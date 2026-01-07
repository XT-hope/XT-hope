"""
Simulink 控制器：通过 MATLAB Engine 启动/停止 Simulink 仿真。

核心功能：
- 启动 MATLAB Engine
- 添加模型目录到 MATLAB path
- 可选执行 bus.m（定义 Simulink.Bus / 数据字典等）
- 加载模型并启动仿真
- 轮询等待 SimulationStatus 到目标状态
- 停止、关闭模型并退出引擎

注意：
- 本模块依赖 `matlab.engine`（MATLAB 提供）；
- Windows 下如果你需要在多线程/COM 环境中使用，可开启 init_com=True（需要 pythoncom）。
"""

from __future__ import annotations

import os
import time
from typing import Optional, Sequence


class SimulinkController:
    """
    通过 MATLAB Engine 控制 Simulink 模型仿真的控制器。

    用法示例：

        ctl = SimulinkController(
            model_path=r"D:/xxx/SC2E.slx",
            bus_m=r"D:/xxx/bus.m",
        )
        with ctl:
            ctl.load()
            ctl.start()
            ctl.wait_status("running", timeout=30)
            ctl.stop()
    """

    def __init__(
        self,
        model_path: str,
        model_name: Optional[str] = None,
        bus_m: Optional[str] = None,
        *,
        init_com: bool = False,
        matlab_startup_options: Optional[Sequence[str]] = None,
    ) -> None:
        self.model_path = os.path.abspath(model_path)
        self.model_name = model_name or os.path.splitext(os.path.basename(self.model_path))[0]
        self.bus_m = os.path.abspath(bus_m) if bus_m else None

        self.init_com = init_com
        self.matlab_startup_options = tuple(matlab_startup_options or ())

        self._eng = None
        self._com_inited = False

    # ----------------------------
    # 生命周期/上下文管理
    # ----------------------------
    def __enter__(self) -> "SimulinkController":
        self.start_engine()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # 尽量释放资源：stop/close/quit 过程中出现异常也不应吞掉原异常
        try:
            self.safe_stop_close()
        finally:
            self.quit_engine()

    # ----------------------------
    # Engine 管理
    # ----------------------------
    @property
    def eng(self):
        if self._eng is None:
            raise RuntimeError("MATLAB Engine 未启动，请先调用 start_engine() 或使用 with SimulinkController(...)。")
        return self._eng

    def start_engine(self) -> None:
        """
        启动 MATLAB Engine，并完成基础环境准备（addpath + 可选 bus.m）。
        """
        if self._eng is not None:
            return

        if self.init_com:
            self._maybe_init_com()

        try:
            import matlab.engine  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ImportError(
                "无法导入 matlab.engine。请确认已安装 MATLAB，并在该 Python 环境中安装/配置 MATLAB Engine for Python。"
            ) from e

        if self.matlab_startup_options:
            self._eng = matlab.engine.start_matlab(*self.matlab_startup_options)
        else:
            self._eng = matlab.engine.start_matlab()

        self._prepare_matlab_paths()
        self._run_bus_if_needed()

    def quit_engine(self) -> None:
        """
        退出 MATLAB Engine。
        """
        if self._eng is None:
            self._maybe_uninit_com()
            return
        try:
            self._eng.quit()
        finally:
            self._eng = None
            self._maybe_uninit_com()

    def _maybe_init_com(self) -> None:
        """
        Windows 下可选的 COM 初始化。
        """
        if self._com_inited:
            return
        try:
            import pythoncom  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ImportError("开启 init_com=True 需要安装/可用 pythoncom（pywin32）。") from e

        pythoncom.CoInitialize()
        self._com_inited = True

    def _maybe_uninit_com(self) -> None:
        if not self._com_inited:
            return
        try:
            import pythoncom  # type: ignore

            pythoncom.CoUninitialize()
        finally:
            self._com_inited = False

    # ----------------------------
    # Simulink 操作
    # ----------------------------
    def load(self) -> None:
        """
        加载 Simulink 模型（推荐在 start() 前调用）。
        """
        self.eng.load_system(self._norm_path(self.model_path), nargout=0)

    def start(self) -> None:
        """
        启动仿真。
        """
        self.eng.set_param(self.model_name, "SimulationCommand", "start", nargout=0)

    def stop(self) -> None:
        """
        停止仿真。
        """
        self.eng.set_param(self.model_name, "SimulationCommand", "stop", nargout=0)

    def close(self, save: bool = False) -> None:
        """
        关闭模型。

        参数:
            save: 是否保存模型（默认不保存）。
        """
        self.eng.close_system(self.model_name, 1 if save else 0, nargout=0)

    def get_status(self) -> str:
        """
        获取 SimulationStatus。
        """
        return str(self.eng.get_param(self.model_name, "SimulationStatus"))

    def wait_status(
        self,
        target: str = "running",
        *,
        timeout: float = 30.0,
        interval: float = 0.05,
    ) -> str:
        """
        轮询等待仿真状态达到 target，返回最终状态（可能因超时未达到）。

        常见 target：
        - "running"
        - "stopped"
        - "paused"
        """
        deadline = time.time() + float(timeout)
        last_status = ""
        while time.time() < deadline:
            last_status = self.get_status()
            if last_status == target:
                return last_status
            time.sleep(float(interval))
        return last_status or self.get_status()

    def safe_stop_close(self) -> None:
        """
        尽最大努力停止并关闭模型（用于 finally/退出场景）。
        """
        if self._eng is None:
            return
        try:
            # stop 可能在模型未加载时失败，因此保护性执行
            self.stop()
        except Exception:
            pass
        try:
            self.close(save=False)
        except Exception:
            pass

    # ----------------------------
    # 内部：路径/脚本处理
    # ----------------------------
    def _prepare_matlab_paths(self) -> None:
        """
        把模型目录加入 MATLAB path。
        """
        model_dir = os.path.dirname(self.model_path)
        self.eng.addpath(self._norm_path(model_dir), nargout=0)

    def _run_bus_if_needed(self) -> None:
        """
        可选执行 bus.m（如果文件存在）。
        """
        if not self.bus_m:
            return
        if not os.path.exists(self.bus_m):
            raise FileNotFoundError(f"bus.m 不存在：{self.bus_m}")
        self.eng.run(self._norm_path(self.bus_m), nargout=0)

    @staticmethod
    def _norm_path(p: str) -> str:
        """
        MATLAB 更稳的路径格式：使用 / 分隔符。
        """
        return p.replace("\\", "/")

