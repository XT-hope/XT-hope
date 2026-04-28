"""
MATLAB 引擎管理模块
用于启动和管理 MATLAB Driving Scenario Designer
"""

import subprocess
import sys
import threading
import time
from typing import Callable, Optional


class MatlabEngineManager:
    """MATLAB 引擎管理器，支持后台运行和自动关闭"""

    def __init__(self):
        self.eng = None
        self._monitor_thread = None
        self._stop_monitor = False
        self._is_running = False

    def start_driving_scenario_designer(
        self,
        scenario_file: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        on_closed_callback: Optional[Callable[[], None]] = None
    ) -> bool:
        """
        启动 MATLAB Driving Scenario Designer

        参数:
            scenario_file: 可选，要加载的场景文件路径（.mat文件）
            status_callback: 状态回调函数，用于更新 UI 状态栏
            on_closed_callback: DSD 关闭后的回调函数

        返回:
            bool: 是否启动成功
        """
        def _notify(message: str):
            if status_callback:
                status_callback(message)
            print(message)

        try:
            import matlab.engine

            _notify("正在启动 MATLAB 引擎...")

            # 启动 MATLAB，background=True 表示在后台运行
            future = matlab.engine.start_matlab(background=True)
            self.eng = future.result()

            _notify("MATLAB 引擎已启动")

            if scenario_file:
                # 将 Windows 路径转换为 MATLAB 兼容格式
                matlab_path = scenario_file.replace("\\", "/")
                _notify("正在打开 Driving Scenario Designer...")
                # 打开 Driving Scenario Designer 并加载场景文件
                self.eng.eval(f"drivingScenarioDesigner('{matlab_path}')", nargout=0)
            else:
                _notify("正在打开 Driving Scenario Designer...")
                self.eng.eval("drivingScenarioDesigner", nargout=0)

            _notify("Driving Scenario Designer 已打开")

            self._is_running = True
            self._stop_monitor = False

            # 启动监控线程
            self._monitor_thread = threading.Thread(
                target=self._monitor_dsd_window,
                args=(status_callback, on_closed_callback),
                daemon=True
            )
            self._monitor_thread.start()

            return True

        except ImportError:
            _notify("未安装 MATLAB Engine API，请在 MATLAB 中运行安装脚本")
            return False
        except Exception as e:
            _notify(f"引擎启动失败: {e}")
            return False

    def _monitor_dsd_window(
        self,
        status_callback: Optional[Callable[[str], None]] = None,
        on_closed_callback: Optional[Callable[[], None]] = None
    ):
        """
        监控 Driving Scenario Designer 窗口状态
        当窗口关闭时自动退出 MATLAB 引擎
        """
        def _notify(message: str):
            if status_callback:
                status_callback(message)

        check_interval = 3  # 检查间隔（秒）
        initial_wait = 5  # 初始等待时间，让 DSD 完全启动

        # 等待 DSD 完全启动
        time.sleep(initial_wait)

        while not self._stop_monitor and self.eng:
            try:
                # 方法1: 检查系统窗口是否存在（Windows 平台）
                window_exists = self._check_window_exists_system()

                if not window_exists:
                    # 窗口已关闭
                    if not self._stop_monitor:
                        _notify("Driving Scenario Designer 已关闭，正在退出 MATLAB 引擎...")
                        self._cleanup()
                        _notify("MATLAB 引擎已退出")
                        # 调用关闭回调
                        if on_closed_callback:
                            try:
                                on_closed_callback()
                            except Exception:
                                pass
                    break

            except Exception as e:
                # 如果检测出错，继续尝试
                pass

            time.sleep(check_interval)

    def _check_window_exists_system(self) -> bool:
        """
        使用系统方法检查 Driving Scenario Designer 窗口是否存在
        支持 Windows 平台
        """
        if sys.platform == 'win32':
            try:
                # 使用 PowerShell 检查窗口
                # drivingScenarioDesigner 窗口标题通常包含 "Driving Scenario Designer"
                result = subprocess.run(
                    [
                        'powershell', '-Command',
                        "Get-Process | Where-Object {$_.MainWindowTitle -like '*Driving Scenario Designer*'} | Select-Object -First 1"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                # 如果找到窗口，输出不为空
                return bool(result.stdout.strip())
            except Exception:
                # 如果 PowerShell 检测失败，尝试备用方法
                return self._check_window_exists_matlab()
        else:
            # 非 Windows 平台使用 MATLAB 方法
            return self._check_window_exists_matlab()

    def _check_window_exists_matlab(self) -> bool:
        """
        使用 MATLAB 命令检查窗口是否存在
        """
        try:
            if not self.eng:
                return False

            # 检查是否有 MATLAB 窗口存在
            # drivingScenarioDesigner 会创建 figure 或 uifigure
            result = self.eng.eval(
                "any(arrayfun(@(x) contains(x.Name, 'Driving Scenario Designer', 'IgnoreCase', true), findall(0, 'Type', 'figure')))",
                nargout=1
            )

            if result:
                return True

            # 备用检查：检查 uifigure（App Designer 应用）
            result = self.eng.eval(
                "any(arrayfun(@(x) contains(x.Name, 'Driving Scenario Designer', 'IgnoreCase', true), findall(0, 'Type', 'figure', 'Visible', 'on')))",
                nargout=1
            )

            return bool(result)

        except Exception:
            # 如果 MATLAB 引擎已断开
            return False

    def _cleanup(self):
        """清理资源"""
        self._is_running = False
        try:
            if self.eng:
                self.eng.quit()
        except:
            pass
        self.eng = None

    def close(self):
        """手动关闭 MATLAB 引擎"""
        self._stop_monitor = True
        self._cleanup()

    def is_running(self) -> bool:
        """检查 MATLAB 引擎是否正在运行"""
        return self._is_running and self.eng is not None


# 全局单例实例
_matlab_engine_instance: Optional[MatlabEngineManager] = None


def get_matlab_engine() -> MatlabEngineManager:
    """获取全局 MATLAB 引擎管理器实例"""
    global _matlab_engine_instance
    if _matlab_engine_instance is None:
        _matlab_engine_instance = MatlabEngineManager()
    return _matlab_engine_instance
