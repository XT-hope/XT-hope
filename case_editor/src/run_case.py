import os
import json
import time
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
 
from concurrent.futures import ThreadPoolExecutor, as_completed
 
from factory import create_controller
from default_system_variable import (
    Simulink,
    ValidatingCANoeController,
    DriverAction,
    FunctionSwitch,
    NM,
)
from check_datatype import validate_case
from trace_parser import BLFSignalExtractor
from commen_signal_in_report import commen_signals
from report_generator import build_report_html, _PLOTLY_INLINE_JS
from ecu_recorder import init_config, start_ecu_recorder, stop_recorder, save_to_local
# from ai_caller import AIDataAnalyzer
from error_manager import RunError
 
 
def _fmt_assert(assert_dict: dict) -> str:
    op = assert_dict.get("op")
    if op == "eq":
        return f"== {assert_dict.get('value')}"
    if op == "neq":
        return f"!= {assert_dict.get('value')}"
    if op == "in":
        return f"in {assert_dict.get('values')}"
    if op == "range":
        return f"range {assert_dict.get('min')} ~ {assert_dict.get('max')}"
    return str(assert_dict)
 
 
def _attach_step_idx(err: Exception, step_idx: int) -> Exception:
    try:
        setattr(err, "step_idx", step_idx)
    except Exception:
        pass
    return err
 
 
def _apply_error_to_steps(report_data: Dict[str, Any], err: Exception) -> None:
    """
    将错误信息回填到对应 step（不新增 “Case Failed”）。
    - 优先使用 err.step_idx（1-based）
    - 若 step_idx > len(steps)，则补齐占位到该 step 再回填（避免盖到前一个 step）
    - 若没有 step_idx，则回填到最后一个 step
    - 若 steps 为空，则新增 Init 失败条目
    """
    steps = report_data.setdefault("steps", [])
    msg = str(err)
    idx = getattr(err, "step_idx", None)
 
    if isinstance(idx, int) and idx >= 1:
        if idx > len(steps):
            while len(steps) < idx:
                steps.append({"name": f"Step {len(steps)+1}", "status": "", "message": ""})
        steps[idx - 1]["status"] = "FAIL"
        steps[idx - 1]["message"] = msg
        return
 
    if steps:
        steps[-1]["status"] = "FAIL"
        steps[-1]["message"] = msg
        return
 
    steps.append({"name": "Init", "status": "FAIL", "message": msg})
 
 
@dataclass
class _CheckTask:
    # config
    signal: str
    assert_dict: dict
    poll_ms: float
    timeout_ms: float
    count: Optional[dict]
    checkInTime_ms: Optional[float]
    after_detect_ms: Optional[float]
    wait_ms: Optional[float]
    async_mode: bool
    origin_step_idx: int
 
    # state
    start_t: float
    next_poll_t: float
    deadline_t: float
    hits: int = 0
    done: bool = False
    fail_exc: Optional[Exception] = None
    last_val: Any = None
    post_delay_end_t: Optional[float] = None
 
    # checkInTime 两段式（detect -> stable）
    detected: bool = False
    stable_end_t: Optional[float] = None
 
    # count params
    need_exact: Optional[int] = None
    need_min: Optional[int] = None
    need_max: Optional[int] = None
 
 
class _BackgroundCheckManager:
    """
    单线程后台 check 调度器（逻辑并发、非多线程）。
 
    - 同一个 step 的多个 checks 同时开始（同一 start_t/next_poll_t）
    - async=true：不阻塞当前 step，但会持续推进；后台失败会立刻终止当前 case（抛 RunError）
    - 前台全部通过后：必须 wait_all() 等待后台任务全部完成才算最终 PASS
    - checkInTime_ms 采用“两段式语义”：
        1) detect：在 timeoutOfCheck_ms 内等到第一次满足断言
        2) stable：从第一次满足开始，连续满足 checkInTime_ms；中途跳变立刻失败
    """
 
    def __init__(self, owner: "Main"):
        self._m = owner
        self._tasks: List[_CheckTask] = []
 
    def clear(self) -> None:
        self._tasks = []
 
    def _ensure_controller(self) -> None:
        if self._m._canoe_controller_for_bg_checks is None:
            raise RunError("Background check manager has no CANoe controller bound")
 
    def add_tasks_from_step(self, step, step_idx: int) -> List[_CheckTask]:
        self._ensure_controller()
        if not step.checks:
            raise _attach_step_idx(RunError(f"step {step_idx}: check step has empty checks"), step_idx)
 
        now = time.monotonic()
        tasks: List[_CheckTask] = []
 
        for ck in step.checks:
            assert_dict = self._m._to_assert_dict(ck.assert_h)
 
            timeout_ms = float(ck.timeoutOfCheck_ms) if ck.timeoutOfCheck_ms is not None else 0.0
            checkInTime_ms = float(ck.checkInTime) if ck.checkInTime is not None else None
 
            # 只填 checkInTime_ms 时，补一个 detect 窗口，避免无限等待
            if (checkInTime_ms is not None and checkInTime_ms > 0.0) and timeout_ms <= 0.0:
                # 设置一个总的超时时间
                timeout_ms = max(5000.0, checkInTime_ms + 2000.0)
 
            if timeout_ms <= 0.0:
                raise _attach_step_idx(
                    RunError(f"step {step_idx}: check for {ck.signal} must set timeoutOfCheck_ms (>0)"),
                    step_idx,
                )
 
            poll_ms = float(self._m.sampling_rate)
            after_ms = float(ck.after_detect.ms) if ck.after_detect is not None else None
            wait_ms = float(ck.wait_ms) if ck.wait_ms is not None else None
            cnt = ck.count if ck.count is not None else None
            async_mode = bool(ck.is_async) if ck.is_async is not None else False
 
            deadline_t = now + timeout_ms / 1000.0
 
            t = _CheckTask(
                signal=ck.signal,
                assert_dict=assert_dict,
                poll_ms=poll_ms,
                timeout_ms=timeout_ms,
                count=cnt,
                checkInTime_ms=checkInTime_ms,
                after_detect_ms=after_ms,
                wait_ms=wait_ms,
                async_mode=async_mode,
                origin_step_idx=step_idx,
                start_t=now,
                next_poll_t=now,  # 同步起跑
                deadline_t=deadline_t,
            )
 
            if cnt:
                if cnt.get("exact") is not None:
                    t.need_exact = int(cnt["exact"])
                if cnt.get("min") is not None:
                    t.need_min = int(cnt["min"])
                if cnt.get("max") is not None:
                    t.need_max = int(cnt["max"])
 
            tasks.append(t)
 
        self._tasks.extend(tasks)
        return tasks
 
    def _complete_task_with_post_delay(self, task: _CheckTask, now: float) -> None:
        post_s = 0.0
        if task.after_detect_ms:
            post_s += float(task.after_detect_ms) / 1000.0
        if task.wait_ms:
            post_s += float(task.wait_ms) / 1000.0
        if post_s > 0.0:
            task.post_delay_end_t = now + post_s
        else:
            task.done = True
 
    def tick_once(self) -> None:
        if not self._tasks:
            return
        self._ensure_controller()
 
        now = time.monotonic()
        cc = self._m._canoe_controller_for_bg_checks
 
        for task in self._tasks:
            if task.done or task.fail_exc is not None:
                continue
 
            # post delay
            if task.post_delay_end_t is not None:
                if now >= task.post_delay_end_t:
                    task.done = True
                continue
 
            # timeout 兜底（覆盖 detect + stable）
            if now >= task.deadline_t:
                err = RunError(
                    f"step {task.origin_step_idx}: Timeout waiting {int(task.timeout_ms)}ms for {task.signal} "
                    f"to satisfy {_fmt_assert(task.assert_dict)}"
                    + (
                        f" and keep stable {int(task.checkInTime_ms or 0)}ms"
                        if (task.checkInTime_ms is not None and task.checkInTime_ms > 0.0)
                        else ""
                    )
                    + f"; hits={task.hits}, last_val={task.last_val}, count={task.count or {}}"
                )
                task.fail_exc = _attach_step_idx(err, task.origin_step_idx)
                continue
 
            # throttle
            if now < task.next_poll_t:
                continue
 
            # read once
            try:
                task.last_val = self._m._read_target(cc, task.signal)
            except Exception as e:
                err = RunError(f"step {task.origin_step_idx}: read {task.signal} failed: {e}")
                task.fail_exc = _attach_step_idx(err, task.origin_step_idx)
                continue
 
            # checkInTime 两段式
            if task.checkInTime_ms is not None and task.checkInTime_ms > 0.0:
                # detect
                if not task.detected:
                    if self._m._assert_ok(task.last_val, task.assert_dict):
                        task.detected = True
                        task.stable_end_t = now + float(task.checkInTime_ms) / 1000.0
                    task.next_poll_t = now + max(0.0, task.poll_ms) / 1000.0
                    continue
 
                # stable
                if not self._m._assert_ok(task.last_val, task.assert_dict):
                    elapsed_ms = int((now - task.start_t) * 1000)
                    err = RunError(
                        f"step {task.origin_step_idx}: checkInTime failed for {task.signal} "
                        f"{_fmt_assert(task.assert_dict)}; need stable {int(task.checkInTime_ms)}ms, "
                        f"broke at ~{elapsed_ms}ms, last_val={task.last_val}"
                    )
                    task.fail_exc = _attach_step_idx(err, task.origin_step_idx)
                    continue
 
                if task.stable_end_t is not None and now >= task.stable_end_t:
                    self._complete_task_with_post_delay(task, now)
                else:
                    task.next_poll_t = now + max(0.0, task.poll_ms) / 1000.0
                continue
 
            # timeout+count（无 checkInTime）
            if self._m._assert_ok(task.last_val, task.assert_dict):
                task.hits += 1
 
                if task.need_max is not None and task.hits > task.need_max:
                    err = RunError(
                        f"step {task.origin_step_idx}: Exceeded max count for {task.signal}: "
                        f"hits={task.hits} > max={task.need_max}"
                    )
                    task.fail_exc = _attach_step_idx(err, task.origin_step_idx)
                    continue
 
                ok = (
                    (task.need_exact is None and task.need_min is None and task.need_max is None)
                    or (task.need_exact is not None and task.hits == task.need_exact)
                    or (task.need_min is not None and task.hits >= task.need_min)
                    or (task.need_max is not None and task.hits <= task.need_max)
                )
                if ok:
                    self._complete_task_with_post_delay(task, now)
                    continue
 
            task.next_poll_t = now + max(0.0, task.poll_ms) / 1000.0
 
    def raise_if_failed(self) -> None:
        for t in self._tasks:
            if t.fail_exc is not None:
                raise t.fail_exc
 
    def cleanup_done(self) -> None:
        self._tasks = [t for t in self._tasks if (not t.done) and (t.fail_exc is None)]
 
    def wait_tasks_done(self, tasks: List[_CheckTask]) -> None:
        if not tasks:
            return
        pending = {id(t) for t in tasks}
        while pending:
            self.tick_once()
            self.raise_if_failed()
 
            for t in self._tasks:
                if id(t) in pending and t.done:
                    pending.remove(id(t))
 
            self.cleanup_done()
            time.sleep(0.005)
 
    def wait_all(self) -> None:
        while self._tasks:
            self.tick_once()
            self.raise_if_failed()
            self.cleanup_done()
            time.sleep(0.005)
 
 
class Main:
    def __init__(
        self,
        case_paths: list[str],
        project_json_path: str,
        project_path: str,
        out_path: str,
        delay_time_after_success_or_failure_for_logging: float = 5000,
        sampling_rate: float = 10,
        adc_version: str = "J6M-1020",
        max_workers=8,
        stop_callback=None,
    ):
        self.case_paths = case_paths
        self.case_datas = [self.load_json_data(path) for path in self.case_paths]
        self.project_data = self.load_json_data(project_json_path)
        self.preset_signals=self.project_data["automation"]["set_preset"]["preset_signals"] if self.project_data["automation"]["set_preset"]["preset_signals"] else None
        self.preset_scene=self.project_data["automation"]["set_preset"]["preset_scene"] if self.project_data["automation"]["set_preset"]["preset_scene"] else None

        # Initialize ECU recorder config from project
        record_config = self.project_data.get("automation", {}).get("record_config", {})
        if record_config:
            init_config(record_config)

        self.sampling_rate = sampling_rate
        self.delay_time_after_success_or_failure_for_logging = delay_time_after_success_or_failure_for_logging

        self.adc_version = adc_version
        self.out_path = out_path
        self.project_path = project_path
        self.ecu_data_path = self.project_path + "/Test Results/" + "/record data/" + self.out_path + "/" + self.adc_version
        # {'CAN 1': 0, 'CAN 2': 1}
        self.bus_name_to_channel = {k: v["channel"] for k, v in self.project_data["canoe"]["dbc_files"].items()}
        self.dbc_paths = {k: self.project_path + "\\" + v["path"] for k, v in self.project_data["canoe"]["dbc_files"].items()}
        # print("DBC Paths:", self.dbc_paths)

        Path(self.ecu_data_path).mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers

        self._canoe_controller_for_bg_checks = None
        self._bg = _BackgroundCheckManager(self)
        self.stop_callback = stop_callback

    def _should_stop(self) -> bool:
        """Check if stop is requested"""
        return self.stop_callback and self.stop_callback()

    def _stat_key(self, path: str):
        s = os.stat(path)
        return (s.st_mtime_ns, s.st_size)

    @lru_cache(maxsize=2048)
    def _load_case(self, path: str, stat_key):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_json_data(self, path: str):
        return self._load_case(path, self._stat_key(path))
 
    def canoe_control(self):
        try:
            canoe_controller = create_controller()
            return ValidatingCANoeController(canoe_controller)
        except Exception as e:
            print(f"Error occurred while creating CANoe controller: {e}")
            return None
 
    def _empty_run(self, canoe_controller, preset_scene_id, preset_scene_runtime):
        #canoe_controller.write_system_variable(FunctionSwitch.CSW_Enable_S, 1)
        canoe_controller.write_system_variable(Simulink.SceneSelect, preset_scene_id)
        if preset_scene_runtime is not None:
            self._sleep_ms(preset_scene_runtime)
        #canoe_controller.write_system_variable(FunctionSwitch.CSW_Enable_S, FunctionSwitch.CSW_Enable_S.initValue)
 
    def auto_execute(self):
        print("=== Automation running ===")
        print("Try to create CANoe controller...")
        canoe_controller = self.canoe_control()
        if canoe_controller is None:
            print("Failed to create CANoe controller. Exiting...")
            return False
        print("Successfully created CANoe controller...")
        self._canoe_controller_for_bg_checks = canoe_controller
 
        try:
            print("Checking measurement status of CANoe...")
            while not canoe_controller.is_measurement_running():
                pass
        except Exception as e:
            print(f"Failed to check measurement status of CANoe: {e}")
            return False
        print("CANoe measurement is running.")

        report_datas: List[Dict[str, Any]] = []

        for i, case_data in enumerate(self.case_datas):
            # Check stop flag before each case
            if self._should_stop():
                remaining = len(self.case_datas) - i
                print(f"收到停止请求，跳过后续 {remaining} 个用例")
                break

            print("#############################################################")
 
            report_data: Dict[str, Any] = {
                "case_id": "",
                "scenario_id": "",
                "scenario_name": "",
                "test_point": "",
                "owner": "",
                "priority": "",
                "signals": {},
                "flow": [],
                "blf_path": "",
                "pass_or_fail": "",
                "steps": [],
                "execution_time": 0.0,
            }
 
            self._bg.clear()
            start_time = time.time()
            sess = None
            case_id = ""
 
            ori_env_sys_var_values: Dict[str, Any] = {}
            use_dynamic = True
            logging_started = False
 
            try:
                case = validate_case(case_data, i)
                case_id = case.case_id
 
                meta = case.meta
                scenario_id = int(meta.scenario_id)
                record = bool(meta.record) if meta.record is not None else None
                ai_analysis = bool(meta.ai_analysis) if meta.ai_analysis is not None else None
                use_preset = bool(meta.use_preset) if meta.use_preset is not None else None
                preset_signals = meta.preset_signals if meta.preset_signals is not None else None
                preset_scene = meta.preset_scene if meta.preset_scene is not None else None
                preset_scene_runtime = meta.preset_scene_runtime if meta.preset_scene_runtime is not None else None
                meta_case_id = meta.case_id

                report_data["case_id"] = case_id
                report_data["scenario_id"] = scenario_id
                report_data["scenario_name"] = meta.scenario_name
                report_data["test_point"] = meta.test_point
                report_data["owner"] = meta.owner
                report_data["priority"] = meta.priority
                report_data["signals"] = meta.signals
                report_data["flow"] = case.flow
                
                print(f"Executing test case {i+1}: {case_id}")
                
                if use_preset is not None:
                    if preset_signals is not None:
                        signals_id = re.findall(r'P\d+', preset_signals)
                        print("查看预设信号并记录其初始值...")
                        for sig_id in signals_id:
                            for s in self.preset_signals:
                                if s['id'] == sig_id:
                                    # 先记后设
                                    if s['signal_name'].split("::")[0] == "env":
                                        try:
                                            asig_value = canoe_controller.read_environment_variable(s['signal_name'].split("::")[-1])
                                        except Exception as e:
                                            print(f"读取预设环境变量初始值失败: {s['signal_name']}, err={e}", flush=True)
                                        ori_env_sys_var_values.setdefault(s['signal_name'], asig_value)
                                        
                                    elif s['signal_name'].split("::")[0] == "sys":
                                        try:
                                            asig_value = canoe_controller.read_system_variable(s['signal_name'].split("::")[-1])
                                        except Exception as e:
                                            print(f"读取预设系统变量初始值失败: {s['signal_name']}, err={e}", flush=True)
                                        ori_env_sys_var_values.setdefault(s['signal_name'], asig_value)

                                    self._write_target(canoe_controller, s['signal_name'], s['signal_value'])
                                    break
                        print("预设信号已设置，且初始值已记录...")
                    if preset_scene is not None:
                        print(f"设置预设场景并运行预设场景{preset_scene}: {preset_scene_runtime}秒...")
                        self._empty_run(canoe_controller,int(preset_scene),preset_scene_runtime)

                
                if record is not None:
                    sess = start_ecu_recorder(case_id, duration_sec=300)
                    print(f"Start recording ECU data for test case {case_id}")
 
                canoe_controller.write_system_variable(Simulink.SceneSelect, scenario_id)
 
                canoe_controller.write_system_variable(Simulink.SceneReset, 0)
                self._sleep_ms(50)
                canoe_controller.write_system_variable(Simulink.SceneReset, Simulink.SceneReset.initValue)
                self._sleep_ms(100)
                canoe_controller.write_system_variable(Simulink.SceneReset, 0)
 
                # if record is not None:
                #     sess = start_ecu_recorder(case_id, duration_sec=300)
                #     print(f"Start recording ECU data for test case {case_id}")
 
                blf_path = canoe_controller.start_logging(
                    os.path.join(self.project_path, "Test Results", "trace_data", self.out_path, self.adc_version),
                    case_id,
                    "test.blf",
                )
                logging_started = True
                report_data["blf_path"] = blf_path
 
                case_steps = Main.order_steps(case.steps, case.flow, case.phase_order)
 
                for step_idx, step in enumerate(case_steps, 1):
                    # 先 append 占位 step_result，确保失败时能回填到正确的 step
                    if step.type == "set":
                        siginfo = "".join([f"{a.signal.split('::')[-1]}={a.value} " for a in step.assignments])
                        step_result = {"name": f"Step {step_idx}: set {siginfo}", "status": "", "message": ""}
                    else:
                        brief = " && ".join(
                            [
                                f"{ck.signal.split('::')[-1]} {_fmt_assert(self._to_assert_dict(ck.assert_h))}"
                                for ck in (step.checks or [])
                            ]
                        )
                        step_result = {"name": f"Step {step_idx}: check {brief}", "status": "", "message": ""}
 
                    report_data["steps"].append(step_result)
 
                    if step.keep_dynamic is not None and not step.keep_dynamic:
                        use_dynamic = False
 
                    # 记录 set 原始值用于恢复（失败只打印，不中断）
                    if step.type == "set":
                        for assi in step.assignments:
                            asig = assi.signal
                            asig_value = None
 
                            if asig.split("::")[0] == "env":
                                try:
                                    asig_value = canoe_controller.read_environment_variable(asig.split("::")[-1])
                                except Exception as e:
                                    print(f"读取原始环境变量失败: {asig}, err={e}", flush=True)
                                ori_env_sys_var_values.setdefault(asig, asig_value)
 
                            elif asig.split("::")[0] == "sys":
                                try:
                                    asig_value = canoe_controller.read_system_variable(asig.split("sys::")[-1])
                                except Exception as e:
                                    print(f"读取原始系统变量失败: {asig}, err={e}", flush=True)
                                ori_env_sys_var_values.setdefault(asig, asig_value)
 
                    # step 前推进后台；后台失败立即终止 case（但会被 except 捕获并记录 FAIL）
                    self._bg.tick_once()
                    self._bg.raise_if_failed()
 
                    print(f"Executing step {step_idx} ...", flush=True)
 
                    try:
                        step_result_done = self.execute_step(
                            canoe_controller=canoe_controller,
                            step=step,
                            step_idx=step_idx,
                        )
                        report_data["steps"][step_idx - 1] = step_result_done
 
                    except RunError as e:
                        # 立刻在控制台打印失败原因（紧跟在 Executing step... 下一行）
                        if not hasattr(e, "step_idx"):
                            try:
                                e.step_idx = step_idx
                            except Exception:
                                pass
                        fail_step = getattr(e, "step_idx", step_idx)
                        print(f"[FAIL] Step {fail_step}: {e}", flush=True)
                        try:
                            e._printed = True
                        except Exception:
                            pass
                        raise
 
                # 前台全部通过后：必须等待后台任务完成，才算最终 PASS
                self._sleep_ms(self.delay_time_after_success_or_failure_for_logging)
                if logging_started:
                    try:
                        canoe_controller.stop_logging()
                        print("Stopped CANoe logging.")
                    except Exception as e:
                        print(f"{e}", flush=True)
                    finally:
                        logging_started = False
                
                if record is not None and sess is not None:
                    stop_recorder(sess)
                    save_to_local(sess=sess, delete_remote=True, base_dir=self.ecu_data_path)
                    print(f"Stopped and Saved ECU data for test case {case_id}")

                self._reset_sys_env_var(canoe_controller, ori_env_sys_var_values, use_dynamic)
 
                self._bg.wait_all()
 
                report_data["execution_time"] = time.time() - start_time
                report_data["pass_or_fail"] = "PASS"
                report_datas.append(report_data)
 
                print(f"Test case success executed: {case_id}")
                print("#############################################################\n")
 
            except RunError as e:
                # 兜底：有些失败会发生在 step 外（例如 delay / wait_all），这里也打印一次
                if not getattr(e, "_printed", False):
                    fail_step = getattr(e, "step_idx", None)
                    if isinstance(fail_step, int):
                        print(f"[FAIL] Step {fail_step}: {e}", flush=True)
                    else:
                        print(f"[FAIL] Case error: {e}", flush=True)
 
                try:
                    self._sleep_ms(self.delay_time_after_success_or_failure_for_logging, suppress_bg_fail=True)
                except Exception:
                    pass
 
                report_data["execution_time"] = time.time() - start_time
                report_data["pass_or_fail"] = "FAIL"
                _apply_error_to_steps(report_data, e)
                report_datas.append(report_data)
 
                if logging_started:
                    try:
                        canoe_controller.stop_logging()
                        print("Stopped CANOE trace logging")
                    except Exception:
                        print(f"{e}", flush=True)
                        
                    logging_started = False
                
                if record is not None and sess is not None:
                    stop_recorder(sess)
                    save_to_local(sess=sess, delete_remote=True, base_dir=self.ecu_data_path)
                    print(f"Stopped and Saved ECU data for test case {case_id}")
                    
                try:
                    self._reset_sys_env_var(canoe_controller, ori_env_sys_var_values, use_dynamic)
                except Exception:
                    pass
 
                print(f"Test case {case_id} failed!!!!!")
                print("#############################################################\n")
                continue
 
            except Exception as e:
                print(f"[FAIL] Unexpected error: {e}", flush=True)
 
                try:
                    self._sleep_ms(self.delay_time_after_success_or_failure_for_logging, suppress_bg_fail=True)
                except Exception:
                    pass
 
                report_data["execution_time"] = time.time() - start_time
                report_data["pass_or_fail"] = "FAIL"
                _apply_error_to_steps(report_data, e)
                report_datas.append(report_data)
 

                if logging_started:
                    try:
                        canoe_controller.stop_logging()
                        print("Stopped CANOE trace logging")
                    except Exception:
                        print(f"{e}", flush=True)
                    logging_started = False
                    
                if record is not None and sess is not None:
                    stop_recorder(sess)
                    save_to_local(sess=sess, delete_remote=True, base_dir=self.ecu_data_path)
                    print(f"Stopped and Saved ECU data for test case {case_id}")
                    
                try:
                    self._reset_sys_env_var(canoe_controller, ori_env_sys_var_values, use_dynamic)
                except Exception:
                    pass
 
                print(f"Test case {case_id} failed!!!!!")
                print("#############################################################\n")
                continue
 
        # 生成报告
        if report_datas:
            print(f"Processing {len(report_datas)} test cases with {self.max_workers} threads...")
            processed_report_datas: List[Dict[str, Any]] = []
 
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_rd = {executor.submit(self._process_single_report_data, rd, ai_analysis): rd for rd in report_datas}
                for future in as_completed(future_to_rd):
                    rd = future_to_rd[future]
                    try:
                        processed_rd = future.result()
                        processed_report_datas.append(processed_rd)
                        print(f"Successfully processed test case: {processed_rd.get('case_id', '')}")
                    except Exception as e:
                        print(f"Error processing test case {rd.get('case_id', '')}: {e}")
                        processed_report_datas.append(rd)
 
            report_datas = processed_report_datas
            report_datas.sort(key=lambda x: x.get("case_id", ""))
 
            genT = datetime.now().strftime("%Y%m%d_%H%M%S")
            report = {
                "reportTitle": f"Automation Test Report for {self.out_path}",
                "generatedAt": genT,
                "author": "xiongtao",
                "cases": [],
            }
            for rd in report_datas:
                report["cases"].append(
                    {
                        "id": rd.get("case_id", ""),
                        "test_point": rd.get("test_point", ""),
                        "status": rd.get("pass_or_fail", ""),
                        "duration_ms": rd.get("execution_time", 0),
                        "signals": {k.split("::")[-1]: v for k, v in rd.get("series", {}).items()},
                        "steps": rd.get("steps", []),
                        "ai_report": rd.get("ai_report", ""),
                    }
                )
 
            try:
                report_path = os.path.join(self.project_path, "Test Results", "report data", self.out_path, self.adc_version)
                Path(report_path).mkdir(parents=True, exist_ok=True)
                html = build_report_html(report, inline_plotly_js=_PLOTLY_INLINE_JS)
                out = Path(f"{report_path}/{self.out_path}_{genT}.html")
                out.write_text(html, encoding="utf-8")
                print(f"success to generate report: {out.resolve()}。")
            except Exception as e:
                print(f"failed to generate report: {e}")
        else:
            print("No test cases were executed. No report will be generated.")
 
    @staticmethod
    def order_steps(case_steps, case_flow, phase_order):
        step_by_id = {s.id: s for s in case_steps}
        if case_flow:
            missing = [sid for sid in case_flow if sid not in step_by_id]
            if missing:
                raise RunError(f"flow references missing step ids: {missing}")
            extras = [s.id for s in case_steps if s.id not in case_flow]
            if extras:
                raise RunError(f"steps not covered by flow: {extras}")
            return [step_by_id[sid] for sid in case_flow]
 
        if phase_order:
            return [s for phase in phase_order for s in case_steps if s.type == phase]
 
        return list(case_steps)
 
    def _write_target(self, canoe_controller, target: str, value: Any) -> None:
        if target.startswith("env::"):
            name = target.split("env::", 1)[1]
            canoe_controller.write_environment_variable(name, value)
        elif target.startswith("sys::"):
            path = target.split("sys::", 1)[1]
            canoe_controller.write_system_variable(path, value)
        else:
            raise RunError(f"unknown signal type: {target}, signal name of set must start with env/sys")
 
    def _sleep_ms(self, ms: float, *, suppress_bg_fail: bool = False) -> None:
        total_s = max(0.0, float(ms)) / 1000.0
        end = time.monotonic() + total_s
        while True:
            self._bg.tick_once()
            if not suppress_bg_fail:
                self._bg.raise_if_failed()
 
            now = time.monotonic()
            if now >= end:
                return
            time.sleep(min(0.02, end - now))
 
    def _read_target(self, canoe_controller, target: str):
        if target.startswith("env::"):
            name = target.split("env::", 1)[1]
            return canoe_controller.read_environment_variable(name)
        if target.startswith("sys::"):
            path = target.split("sys::", 1)[1]
            return canoe_controller.read_system_variable(path)
        if target.startswith("sig::"):
            path = target.split("sig::", 1)[1]
            return canoe_controller.read_signal(path)
        raise RunError(f"unknown target: {target}")
 
    def _assert_ok(self, actual, assert_h: dict) -> bool:
        op = assert_h.get("op")
        if op == "eq":
            return actual == assert_h.get("value")
        if op == "neq":
            return actual != assert_h.get("value")
        if op == "in":
            vals = assert_h.get("values", assert_h.get("value"))
            return isinstance(vals, (list, tuple, set)) and actual in vals
        if op == "range":
            lo = assert_h.get("min")
            hi = assert_h.get("max")
            try:
                x = float(actual)
            except Exception:
                return False
            return (lo is None or x >= float(lo)) and (hi is None or x <= float(hi))
        raise RunError(f"unsupported op: {op}")
 
    def _to_assert_dict(self, assert_h_obj) -> dict:
        if assert_h_obj is None:
            return {}
        if isinstance(assert_h_obj, dict):
            return assert_h_obj
        val = getattr(assert_h_obj, "value", None)
        d = {"op": getattr(assert_h_obj, "op", None)}
        if isinstance(val, (list, tuple, set)):
            d["values"] = list(val)
        elif isinstance(val, dict):
            d.update(val)
        else:
            d["value"] = val
        return d
 
    def _check_distance(self, canoe_controller, step_idx, rel_lon_distance=None, rel_lat_distance=None):
        rel_lon_distance_value = rel_lon_distance.value if rel_lon_distance is not None else None
        rel_lon_distance_op = rel_lon_distance.op if rel_lon_distance is not None else None
        rel_lat_distance_value = rel_lat_distance.value if rel_lat_distance is not None else None
        rel_lat_distance_op = rel_lat_distance.op if rel_lat_distance is not None else None
 
        if rel_lon_distance is not None and rel_lat_distance is None:
            while True:
                cur_rel_lon_dis = canoe_controller.read_system_variable(Simulink.obj_dist_lon)
                if rel_lon_distance_op == "==" and cur_rel_lon_dis == rel_lon_distance_value:
                    break
                if rel_lon_distance_op == ">=" and cur_rel_lon_dis >= rel_lon_distance_value:
                    break
                if rel_lon_distance_op == "<=" and cur_rel_lon_dis <= rel_lon_distance_value:
                    break
                self._bg.tick_once()
                self._bg.raise_if_failed()
                time.sleep(0.02)
 
        elif rel_lon_distance is None and rel_lat_distance is not None:
            while True:
                cur_rel_lat_dis = canoe_controller.read_system_variable(Simulink.obj_dist_lat)
                if rel_lat_distance_op == "==" and cur_rel_lat_dis == rel_lat_distance_value:
                    break
                if rel_lat_distance_op == ">=" and cur_rel_lat_dis >= rel_lat_distance_value:
                    break
                if rel_lat_distance_op == "<=" and cur_rel_lat_dis <= rel_lat_distance_value:
                    break
                self._bg.tick_once()
                self._bg.raise_if_failed()
                time.sleep(0.02)
 
        elif rel_lon_distance is not None and rel_lat_distance is not None:
            while True:
                cur_rel_lon_dis = canoe_controller.read_system_variable(Simulink.obj_dist_lon)
                cur_rel_lat_dis = canoe_controller.read_system_variable(Simulink.obj_dist_lat)
 
                ok_lon = (
                    (rel_lon_distance_op == "==" and cur_rel_lon_dis == rel_lon_distance_value)
                    or (rel_lon_distance_op == ">=" and cur_rel_lon_dis >= rel_lon_distance_value)
                    or (rel_lon_distance_op == "<=" and cur_rel_lon_dis <= rel_lon_distance_value)
                )
                ok_lat = (
                    (rel_lat_distance_op == "==" and cur_rel_lat_dis == rel_lat_distance_value)
                    or (rel_lat_distance_op == ">=" and cur_rel_lat_dis >= rel_lat_distance_value)
                    or (rel_lat_distance_op == "<=" and cur_rel_lat_dis <= rel_lat_distance_value)
                )
                if ok_lon and ok_lat:
                    break
                self._bg.tick_once()
                self._bg.raise_if_failed()
                time.sleep(0.02)
 
    def execute_step(self, canoe_controller, step, step_idx):
        # step 前推进后台；后台失败立即终止 case
        self._bg.tick_once()
        self._bg.raise_if_failed()
 
        if step.type == "set":
            siginfo = "".join([f"{a.signal.split('::')[-1]}={a.value} " for a in step.assignments])
            step_result = {"name": f"Step {step_idx}: set {siginfo}", "status": "", "message": ""}
 
            try:
                for a in step.assignments:
                    if step.keep_dynamic is not None and not step.keep_dynamic:
                        canoe_controller.write_system_variable(Simulink.dynamic_disconnect, 1)
 
                    self._write_target(canoe_controller, a.signal, a.value)
 
                    # 每次 set 后推进后台
                    self._bg.tick_once()
                    self._bg.raise_if_failed()
 
                if step.rel_lon_distance is not None or step.rel_lat_distance is not None:
                    self._check_distance(canoe_controller, step_idx, step.rel_lon_distance, step.rel_lat_distance)
 
                if step.wait_ms is not None:
                    self._sleep_ms(step.wait_ms)
 
                step_result["status"] = "PASS"
                step_result["message"] = "~"
                return step_result
 
            except RunError as e:
                raise _attach_step_idx(e, step_idx)
            except Exception as e:
                raise _attach_step_idx(RunError(f"step {step_idx}: Error set target {siginfo}: {e}"), step_idx)
 
        # check step：同一步并发启动多个 checks
        if not step.checks:
            raise _attach_step_idx(RunError(f"step {step_idx}: check step has empty checks"), step_idx)
 
        brief = " && ".join(
            [f"{ck.signal.split('::')[-1]} {_fmt_assert(self._to_assert_dict(ck.assert_h))}" for ck in step.checks]
        )
        step_result = {"name": f"Step {step_idx}: check {brief}", "status": "", "message": ""}
 
        tasks = self._bg.add_tasks_from_step(step, step_idx)
        sync_tasks = [t for t in tasks if not t.async_mode]
        async_tasks = [t for t in tasks if t.async_mode]
 
        self._bg.wait_tasks_done(sync_tasks)
 
        step_result["status"] = "PASS"
        step_result["message"] = "async checks running in background" if async_tasks else "~"
        return step_result
 
    def _reset_sys_env_var(self, canoe_controller, vars: dict, user_dynamic=True):
        for var_name, var_value in vars.items():
            if var_name.startswith("env::"):
                canoe_controller.write_environment_variable(var_name.split("::")[-1], var_value)
            elif var_name.startswith("sys::"):
                canoe_controller.write_system_variable(var_name.split("sys::")[-1], var_value)
 
        if not user_dynamic:
            canoe_controller.write_system_variable(Simulink.dynamic_disconnect, 0)

        # canoe_controller.write_system_variable(DriverAction.driverspeed, 0)

        canoe_controller.write_system_variable(Simulink.SceneReset, 0)
        self._sleep_ms(50, suppress_bg_fail=True)
        canoe_controller.write_system_variable(Simulink.SceneReset, Simulink.SceneReset.initValue)
        self._sleep_ms(50, suppress_bg_fail=True)
        canoe_controller.write_system_variable(Simulink.SceneReset, 0)

    def _process_single_report_data(self, rd, ai_analysis):
        """处理单个测试用例的信号提取"""
        try:
            be = BLFSignalExtractor(
                dbc_paths=self.dbc_paths,
                decode_choices=False,
                scaling=True,
                bus_name_to_channel=self.bus_name_to_channel,
            )
        except Exception as e:
            print(f"Failed to create BLFSignalExtractor: {e}")
            return rd
 
        tokens: List[str] = []
        for sigs in rd.get("signals", {}).values():
            for sig in sigs:
                if sig.startswith("env::"):
                    tokens.append(sig.split("env::")[-1])
                elif sig.startswith("sig::"):
                    tokens.append(sig.split("sig::")[-1])
 
        if tokens:
            for cs in commen_signals:
                tokens.append(cs)
        else:
            rd["series"] = {}
            print(f"Test case {rd.get('case_id','')} failed: no valid signals found")
            return rd
 
        if rd.get("blf_path") and rd.get("pass_or_fail"):
            try:
                series = be.collect_grouped_series_by_tokens(
                    blf_path=rd["blf_path"],
                    tokens=tokens,
                    time_origin="global_min",
                    time_unit="s",
                    time_decimals=6,
                )
            except Exception as e:
                series = {}
                print(f"Failed to collect signal series for test case {rd.get('case_id','')}: {e}")
            rd["series"] = series

        # if ai_analysis is not None:
        #     ai_analyzer = AIDataAnalyzer(self.config.get_ai_config(), rd)
        #     ai_resp = ai_analyzer.analyze()
        #     rd["ai_report"] = ai_resp if ai_resp is not None else ""
        # else:
        rd["ai_report"] = ""
        return rd
 
 
if __name__ == "__main__":
    channel_conf_path = os.path.join(
        os.path.dirname(__file__),
        "case_handler",
        "config_file",
        "channel_configuration.json",
    )
    with open(channel_conf_path, "r", encoding="utf-8") as f:
        channel_data = json.load(f)
 
    dbc_paths = {ch: channel["dbc_path"] for ch, channel in channel_data.items() if channel.get("dbc_path")}
    bus_name_to_channel = {
        ch: channel["channel"] for ch, channel in channel_data.items() if channel.get("channel") is not None
    }
 
    app = Main(
        "test", #"csw_20260302",
        dbc_paths=dbc_paths,
        func_control_active_gap=20000,
        delay_time_after_success_or_failure_for_logging=3000,
        sampling_rate=10,
        bus_name_to_channel=bus_name_to_channel,
        adc_version="J6M-0324",
        id_of_empty_scene=70,
        save_ecu_record=True,
        config_path="D:\\Test\\Automation2\\case_handler\\config_file\\config.json",
    )
    app.auto_execute()
