from __future__ import annotations
import sys
import logging
from logging.handlers import RotatingFileHandler
import re
import time
import threading
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import List, Tuple, Optional
import json
# from .logger import ScriptLogger
# loggerMain = ScriptLogger(verbose=True)

import paramiko

# ============ 默认配置（兜底） ============
_DEFAULT_CONFIG = {
    "connection": {
        "host": "xx.xx.xx.xx",
        "port": xx,
        "user": "xxxxx",
        "user_pass": "xxxxx",
        "root_pass": "xxxxx"
    },
    "paths": {
        "work_dir": "/app",
        "init_script": "./script/.release.bash",
        "remote_glob_prefix": "2025",
        "local_base": "./ecu_records"
    },
    "timeouts": {
        "login": 30,
        "command": 40,
        "sftp": 300
    },
    "behavior": {
        "post_start_sleep_sec": 1.0,
        "post_stop_sleep_sec": 1.0,
        "drain_log_sample": False
    },
    "logging": {
        "log_file": "ecu_recorder.log",
        "max_bytes": 2097152,
        "backup_count": 3,
        "mask_secrets": True
    }
}

# 全局配置变量
_config = _DEFAULT_CONFIG.copy()

# 全局变量声明
HOST: str
PORT: int
USER: str
USER_PASS: str
ROOT_PASS: str
WORK_DIR: str
INIT_SCRIPT: str
REMOTE_GLOB_PREFIX: str
LOCAL_BASE: str
LOGIN_TIMEOUT: int
CMD_TIMEOUT: int
SFTP_TIMEOUT: int
POST_START_SLEEP_SEC: float
POST_STOP_SLEEP_SEC: float
DRAIN_LOG_SAMPLE: bool
LOG_FILE: str
LOG_MAX_BYTES: int
LOG_BACKUP_COUNT: int
MASK_SECRETS_IN_LOG: bool
DELETE_WAIT_TIMEOUT: int = 300


def init_config(config: dict) -> None:
    """
    初始化配置，替代从文件读取。
    在调用任何 API 前调用此函数。

    Args:
        config: 配置字典，结构同 _DEFAULT_CONFIG
    """
    global _config
    _config = config
    _setup_globals()


def _setup_globals() -> None:
    """根据 _config 设置全局变量"""
    global HOST, PORT, USER, USER_PASS, ROOT_PASS
    global WORK_DIR, INIT_SCRIPT, REMOTE_GLOB_PREFIX, LOCAL_BASE
    global LOGIN_TIMEOUT, CMD_TIMEOUT, SFTP_TIMEOUT
    global POST_START_SLEEP_SEC, POST_STOP_SLEEP_SEC, DRAIN_LOG_SAMPLE
    global LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, MASK_SECRETS_IN_LOG

    conn = _config.get("connection", {})
    HOST = conn.get("host", "192.168.195.3")
    PORT = conn.get("port", 22)
    USER = conn.get("user", "idc")
    USER_PASS = conn.get("user_pass", "xxxx")
    ROOT_PASS = conn.get("root_pass", "xxxx")

    paths = _config.get("paths", {})
    WORK_DIR = paths.get("work_dir", "/app")
    INIT_SCRIPT = paths.get("init_script", "./script/.release.bash")
    REMOTE_GLOB_PREFIX = paths.get("remote_glob_prefix", "2025")
    LOCAL_BASE = paths.get("local_base", "./ecu_records")

    timeouts = _config.get("timeouts", {})
    LOGIN_TIMEOUT = timeouts.get("login", 30)
    CMD_TIMEOUT = timeouts.get("command", 40)
    SFTP_TIMEOUT = timeouts.get("sftp", 300)

    behavior = _config.get("behavior", {})
    POST_START_SLEEP_SEC = behavior.get("post_start_sleep_sec", 1.0)
    POST_STOP_SLEEP_SEC = behavior.get("post_stop_sleep_sec", 1.0)
    DRAIN_LOG_SAMPLE = behavior.get("drain_log_sample", False)

    logging_cfg = _config.get("logging", {})
    LOG_FILE = logging_cfg.get("log_file", "ecu_recorder.log")
    LOG_MAX_BYTES = logging_cfg.get("max_bytes", 2097152)
    LOG_BACKUP_COUNT = logging_cfg.get("backup_count", 3)
    MASK_SECRETS_IN_LOG = logging_cfg.get("mask_secrets", True)


# 模块加载时用默认值初始化
_setup_globals()
# ============ 日志器（INFO->stdout, WARN/ERROR->stderr, 文件全量） ============
logger = logging.getLogger("ecu_recorder")
logger.setLevel(logging.INFO)
for h in list(logger.handlers):
    logger.removeHandler(h)

fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

ch_out = logging.StreamHandler(stream=sys.stdout)
ch_out.setLevel(logging.INFO)
ch_out.setFormatter(fmt)
logger.addHandler(ch_out)

ch_err = logging.StreamHandler(stream=sys.stderr)
ch_err.setLevel(logging.WARNING)
ch_err.setFormatter(fmt)
logger.addHandler(ch_err)

fh = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(fmt)
logger.addHandler(fh)
logger.setLevel(logging.CRITICAL)


def _mask(s: str) -> str:
    if not MASK_SECRETS_IN_LOG:
        return s
    for secret in (USER_PASS, ROOT_PASS):
        if secret:
            s = s.replace(secret, "*" * 8)
    return s

_ansi_re = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]|\x1b\[\?2004[hl]|\x1b\][^\x07]*\x07")
def _clean(txt: str) -> str:
    txt = _ansi_re.sub("", txt)
    return txt.replace("\r", "")

def _idle_sleep(chan: paramiko.Channel, seconds: float):
    """时间等待 + 丢弃回显，防阻塞。"""
    end = time.time() + seconds
    while time.time() < end:
        if chan.recv_ready():
            try:
                _ = chan.recv(4096)
            except Exception:
                break
        else:
            time.sleep(0.05)


def _wait_for_marker(chan: paramiko.Channel, marker: str, timeout: float) -> bool:
    """
    简单 marker 等待：用于确认某条命令执行结束（例如 rm 完成）。
    只匹配一个固定字符串，不做复杂正则。
    """
    logger.info("WAIT for marker: %s (timeout=%.1fs)", marker, timeout)
    end = time.time() + timeout
    buf = ""
    while time.time() < end:
        if chan.recv_ready():
            try:
                raw = chan.recv(4096).decode("utf-8", errors="ignore")
            except Exception:
                break
            cleaned = _clean(raw)
            buf += cleaned
            tail = cleaned[-200:].replace("\n", "\\n")
            if tail:
                logger.info("<< %s", tail)
            if marker in cleaned:
                logger.info("== Marker '%s' detected", marker)
                return True
        else:
            time.sleep(0.05)
    logger.warning("!! WAIT marker timeout: %s | tail=%s", marker, buf[-300:])
    return False


@dataclass
class Session:
    ssh: paramiko.SSHClient
    chan: paramiko.Channel              # root 交互 shell
    testcase: str
    started_ts: str
    drainer: Optional[threading.Thread] = None
    drain_flag: Optional[threading.Event] = None


# ============ “排水”线程：持续读取回显、丢弃（可选采样日志） ============
def _start_drainer(chan: paramiko.Channel) -> Tuple[threading.Thread, threading.Event]:
    stop_evt = threading.Event()

    def run():
        buf_accum = ""
        last_log = time.time()
        while not stop_evt.is_set():
            try:
                if chan.recv_ready():
                    data = chan.recv(4096)
                    if not data:
                        time.sleep(0.02)
                        continue
                    if DRAIN_LOG_SAMPLE:
                        try:
                            txt = _clean(data.decode("utf-8", errors="ignore"))
                            buf_accum += txt
                            # 每 2 秒采样打印末尾 160 字符
                            if time.time() - last_log > 2:
                                tail = buf_accum[-160:].replace("\n", "\\n")
                                if tail:
                                    logger.debug("<< %s", tail)
                                buf_accum = buf_accum[-1600:]  # 限制内存
                                last_log = time.time()
                        except Exception:
                            pass
                else:
                    time.sleep(0.02)
            except Exception:
                break

    th = threading.Thread(target=run, name="SSHDrain", daemon=True)
    th.start()
    return th, stop_evt


# ============ 交互：登录到 root，mount+source ============
def _open_root_shell() -> Tuple[paramiko.SSHClient, paramiko.Channel]:
    logger.info("SSH connecting to %s@%s:%s ...", USER, HOST, PORT)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, PORT, USER, USER_PASS, timeout=LOGIN_TIMEOUT, look_for_keys=False, allow_agent=False)
    logger.info("SSH connected.")

    chan = ssh.invoke_shell(term="vt100")
    chan.settimeout(CMD_TIMEOUT)

    def send(cmd: str):
        logger.info(">> %s", _mask(cmd)); chan.send(cmd + "\n")

    def wait_for(patterns: List[str], timeout: int, label: str) -> int:
        buf = ""; regs = [re.compile(p, re.MULTILINE) for p in patterns]; end = time.time() + timeout
        while time.time() < end:
            if chan.recv_ready():
                raw = chan.recv(4096).decode("utf-8", errors="ignore")
                cleaned = _clean(raw); buf += cleaned
                tail = cleaned[-200:].replace("\n", "\\n")
                if tail: logger.info("<< %s", tail)
                for i, rgx in enumerate(regs):
                    if rgx.search(buf):
                        logger.info("== Matched[%d]: %s", i, patterns[i]); return i
            else:
                time.sleep(0.03)
        logger.error("!! WAIT TIMEOUT for %s | patterns=%s | tail=%s", label or "<no-label>", patterns, buf[-300:])
        raise TimeoutError(f"wait_for timeout. label={label}, patterns={patterns}")

    # ready
    send("echo __READY__"); wait_for([r"^__READY__$"], CMD_TIMEOUT, "READY")
    # 用户态净化
    send('export TERM=vt100; export LC_ALL=C; unset LS_COLORS; echo __ENV_OK__')
    wait_for([r"^__ENV_OK__$"], CMD_TIMEOUT, "ENV1")
    # cd /app
    send(f"cd {WORK_DIR} && echo __CD_OK__ || echo __CD_FAIL__")
    i = wait_for([r"^__CD_OK__$", r"^__CD_FAIL__$"], CMD_TIMEOUT, "CD")
    if i == 1: raise RuntimeError(f"cd {WORK_DIR} 失败")
    # su -
    send("su -")
    wait_for([r"[Pp]assword:", r"密码[:：]"], CMD_TIMEOUT, "SU ASK")
    send(ROOT_PASS)
    wait_for([r"#\s*$"], CMD_TIMEOUT, "SU PROMPT")
    # root 净化
    send('export TERM=vt100; export LC_ALL=C; unset LS_COLORS; echo __SU_ENV_OK__')
    wait_for([r"^__SU_ENV_OK__$"], CMD_TIMEOUT, "ENV2")
    # remount（注意逗号）
    send("mount -o remount,rw /app && echo __MNT_OK__ || echo __MNT_FAIL__")
    i = wait_for([r"^__MNT_OK__$", r"^__MNT_FAIL__$"], CMD_TIMEOUT, "REMOUNT")
    if i == 1: raise RuntimeError("remount 失败")
    # source 初始化脚本（回到 /app 再 source）
    send(f"cd {WORK_DIR} && source {INIT_SCRIPT} && echo __SRC_OK__ || echo __SRC_FAIL__")
    i = wait_for([r"^__SRC_OK__$", r"^__SRC_FAIL__$"], CMD_TIMEOUT, "SOURCE")
    if i == 1: raise RuntimeError(f"执行 {INIT_SCRIPT} 失败")

    return ssh, chan

# ============ 本地重命名 ============
def _rename_local(out_dir: Path, testcase: str, ts: str):
    files = sorted([p for p in out_dir.iterdir() if p.is_file()])
    for idx, f in enumerate(files, start=1):
        dest = f.with_name(f"{testcase}_{ts}_{idx}{f.suffix}.record")
        if dest.exists():
            try: dest.unlink()
            except Exception: pass
        try:
            f.rename(dest)
        except Exception:
            shutil.copy2(f, dest)
            try: f.unlink()
            except Exception: pass
        logger.info("Renamed: %s -> %s", f.name, dest.name)

# ============ 三个 API ============
def start_ecu_recorder(testcase_name: str, duration_sec: int | None = None) -> Session:

    ssh, chan = _open_root_shell()

    def send(cmd: str):
        logger.info(">> %s", _mask(cmd))
        chan.send(cmd + "\n")

    ts = time.strftime("%Y%m%d_%H%M%S")
    logger.info("=== START recorder | testcase=%s | ts=%s ===", testcase_name, ts)

    # 关键：前台运行（不使用 setsid/nohup，不断开 stdin）
    # 之后由我们发送 Ctrl+C 停止
    send(f"cd {WORK_DIR} && ./cyber_recorder record -a")

    # 启动通道“排水”线程，持续读取输出，避免阻塞
    drainer, flag = _start_drainer(chan)

    # 给程序 1s 缓冲
    _idle_sleep(chan, POST_START_SLEEP_SEC)

    return Session(ssh=ssh, chan=chan, testcase=testcase_name, started_ts=ts, drainer=drainer, drain_flag=flag)


def stop_recorder(sess: Session, kill_by_name_fallback: bool = True):
    """
    停止：向通道发送 Ctrl+C（优雅退出）；可选名称兜底强杀（INT/TERM/KILL）。
    """
    logger.info("=== STOP recorder | ts=%s ===", sess.started_ts)
    chan = sess.chan

    # 1) 发送 Ctrl+C
    try:
        logger.info(">> <CTRL-C>")
        chan.send('\x03')  # Ctrl+C
    except Exception as e:
        logger.warning("Send Ctrl+C failed: %s", e)

    # 2) 短等待，让程序退出、落盘
    _idle_sleep(chan, POST_STOP_SLEEP_SEC)

    # 3) 兜底：按名称干掉还在跑的 recorder（有些场景需要）
    if kill_by_name_fallback:
        try:
            logger.info(">> fallback kill-by-name (INT/TERM/KILL)")
            chan.send("pkill -INT  -f 'cyber_recorder.*record' 2>/dev/null || true\n")
            _idle_sleep(chan, 0.3)
            chan.send("pkill -TERM -f 'cyber_recorder.*record' 2>/dev/null || true\n")
            _idle_sleep(chan, 0.3)
            chan.send("pkill -KILL -f 'cyber_recorder.*record' 2>/dev/null || true\n")
            _idle_sleep(chan, 0.3)

            # BusyBox 兼容：没有 pkill 的情况下，用 ps|grep|awk|xargs
            fallback = (
                "ps -ef 2>/dev/null | grep -E 'cyber_recorder.*record' | grep -v grep | "
                "awk '{print $2}' | xargs -r kill -INT  2>/dev/null\n"
                "ps -ef 2>/dev/null | grep -E 'cyber_recorder.*record' | grep -v grep | "
                "awk '{print $2}' | xargs -r kill -TERM 2>/dev/null\n"
                "ps -ef 2>/dev/null | grep -E 'cyber_recorder.*record' | grep -v grep | "
                "awk '{print $2}' | xargs -r kill -KILL 2>/dev/null\n"
            )
            chan.send(fallback)
            _idle_sleep(chan, 0.5)
        except Exception as e:
            logger.warning("fallback kill failed: %s", e)

    # 4) 关掉“排水”线程
    try:
        if sess.drain_flag:
            sess.drain_flag.set()
        if sess.drainer and sess.drainer.is_alive():
            sess.drainer.join(timeout=1.0)
    except Exception:
        pass

# def save_to_local(sess: Session, delete_remote: bool = True, base_dir: str = None ) -> Path:
#     """
#     下载 /app/<prefix>* → {LOCAL_BASE}/{ts}/，重命名；用 root shell 删除远端。
#     """
#     logger.info("=== SAVE to local | ts=%s | testcase=%s ===", sess.started_ts, sess.testcase)
#     sftp = sess.ssh.open_sftp()
#     sftp.get_channel().settimeout(SFTP_TIMEOUT)
#
#     names = [name for name in sftp.listdir(WORK_DIR) if name.startswith(REMOTE_GLOB_PREFIX)]
#     logger.info("Remote files: %s", names)
#
#     out_dir = Path(base_dir) / sess.testcase
#     out_dir.mkdir(parents=True, exist_ok=True)
#
#     for name in names:
#         remote_path = f"{WORK_DIR}/{name}"
#         print(f"++++++++++++++++remote_path is {remote_path}+++++++++++++++++++++++++++++++++++")
#         local_path = out_dir / name
#         logger.info("Downloading: %s -> %s", remote_path, local_path)
#         sftp.get(remote_path, str(local_path))
#
#     _rename_local(out_dir, sess.testcase, sess.started_ts)
#
#     if delete_remote:
#         chan = sess.chan
#         try:
#             logger.info(">> rm remote traces with marker")
#             # 加上 echo __DEL_DONE__，用于确认命令已执行完成
#             marker = "__DEL_DONE__"
#             cmd = f"cd {WORK_DIR} && rm -f {REMOTE_GLOB_PREFIX}* 2>/dev/null || true; echo {marker}"
#             chan.send(cmd + "\n")
#             # 阻塞等待，直到收到 marker 或超时
#             _wait_for_marker(chan, marker, DELETE_WAIT_TIMEOUT)
#         except Exception as e:
#             logger.warning("remote rm failed: %s", e)
#
#     # 关闭会话
#     try:
#         sess.chan.close()
#     except Exception:
#         pass
#     try:
#         sess.ssh.close()
#     except Exception:
#         pass
#
#     logger.info("=== DONE | saved dir: %s ===", out_dir)
#     return out_dir
def save_to_local(sess: Session, delete_remote: bool = True, base_dir: str = None) -> Path:
    logger.info("=== SAVE to local | ts=%s | testcase=%s ===", sess.started_ts, sess.testcase)
    sftp = sess.ssh.open_sftp()
    sftp.get_channel().settimeout(SFTP_TIMEOUT)

    names = [name for name in sftp.listdir(WORK_DIR) if name.startswith(REMOTE_GLOB_PREFIX)]
    logger.info("Remote files to download: %s", names)

    out_dir = Path(base_dir) / sess.testcase
    # out_dir = Path(LOCAL_BASE) / sess.started_ts
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in names:
        remote_path = f"{WORK_DIR}/{name}"
        local_path = out_dir / name
        logger.info("Downloading: %s -> %s", remote_path, local_path)
        sftp.get(remote_path, str(local_path))
        logger.info("Downloaded: %s", local_path)


    _rename_local(out_dir, sess.testcase, sess.started_ts)


    if delete_remote:
        chan = sess.chan
        deadline = time.time() + DELETE_WAIT_TIMEOUT

        while True:
            remaining = [name for name in sftp.listdir(WORK_DIR) if name.startswith(REMOTE_GLOB_PREFIX)]

            if not remaining:
                logger.info("Remote traces all removed.")
                break

            if time.time() > deadline:
                logger.warning(
                    "remote rm timeout after %.1fs, still remaining: %s",
                    DELETE_WAIT_TIMEOUT, remaining
                )
                break

            logger.info("Remote traces still exist, try rm. remaining=%s", remaining)

            try:
                cmd = f"cd {WORK_DIR} && rm -f {REMOTE_GLOB_PREFIX}* 2>/dev/null || true"
                logger.info(">> %s", cmd)
                chan.send(cmd + "\n")
            except Exception as e:
                logger.warning("remote rm send failed: %s", e)
                break

            _idle_sleep(chan, 0.5)

        logger.info("Remote rm phase finished.")

    try:
        sess.chan.close()
    except Exception:
        pass
    try:
        sess.ssh.close()
    except Exception:
        pass

    logger.info("=== DONE | saved dir: %s ===", out_dir)
    return out_dir
