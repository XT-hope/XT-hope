from __future__ import annotations
from typing import Mapping, Sequence, Dict, List, Tuple, Set, Optional
import re

from can.io import BLFReader
import cantools


class BLFSignalExtractor:
    """
    - dbc_paths: {'CAN 1': 'xxx.dbc', 'CAN 2': 'yyy.dbc'}
    - token:     'CAN 1::Media_0x32B::CSW_Enable_S'
    - 输出:      {token: [(t, v), ...]}，按时间升序
    - 时间归一化: time_origin in {'keep','global_min'}，单位 s/ms/us（默认 s），默认保留6位小数
    """

    _TOKEN_RE = re.compile(r"\s*(CAN\s*\d+)\s*::\s*([^:]+?)\s*::\s*([^:]+?)\s*")

    def __init__(
        self,
        dbc_paths: Mapping[str, str],
        *,
        decode_choices: bool = False,
        scaling: bool = True,
        bus_name_to_channel: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.decode_choices = decode_choices
        self.scaling = scaling
        self.db_by_bus: Dict[str, cantools.database.can.database.Database] = {}
        self.msg_by_bus_name: Dict[str, Dict[str, cantools.database.can.Message]] = {}
        self.bus_to_channel: Dict[str, int] = dict(bus_name_to_channel or {})
        for bus, path in dbc_paths.items():
            db = cantools.database.load_file(path)
            self.db_by_bus[bus] = db
            self.msg_by_bus_name[bus] = {m.name: m for m in db.messages}

    def collect_grouped_series_by_tokens(
        self,
        *,
        blf_path: str,
        tokens: Sequence[str],
        channels: Optional[Set[int]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        time_origin: str = "global_min",
        time_unit: str = "s",
        time_decimals: int = 6,
    ) -> Dict[str, List[Tuple[float, float]]]:
        # 1) 预编译 token -> (bus, msg_def, sig_name, key)，并构建 id29 -> entries
        id_to_entries: Dict[int, List[Tuple[str, cantools.database.can.Message, str, str]]] = {}
        used_buses: Set[str] = set()
        for tok in tokens:
            m = self._TOKEN_RE.fullmatch(tok)
            print(tok)
            if not m:
                raise ValueError(f"无法解析 token: {tok}")
            bus, msg_name, sig_name = m.group(1), m.group(2), m.group(3)
            db = self.db_by_bus.get(bus)
            if db is None:
                raise KeyError(f"未知总线: {bus}")
            msg_def = self.msg_by_bus_name[bus].get(msg_name)

            if msg_def is None:
                raise KeyError(f"总线 {bus} 的消息未找到: {msg_name}")
            if sig_name not in {s.name for s in msg_def.signals}:
                raise KeyError(f"消息 {msg_def.name} 中不存在信号: {sig_name}")

            id29 = msg_def.frame_id & 0x1FFFFFFF
            id_to_entries.setdefault(id29, []).append((bus, msg_def, sig_name, tok))
            used_buses.add(bus)

        # 2) 计算有效通道（若未显式给 channels，按 bus_to_channel 推断）
        if channels is not None:
            effective_channels: Optional[Set[int]] = set(channels)
        else:
            mapped = {self.bus_to_channel[b] for b in used_buses if b in self.bus_to_channel}
            effective_channels = mapped if mapped else None

        # 3) 读取 BLF，解码并聚合
        grouped: Dict[str, List[Tuple[float, float]]] = {}
        with BLFReader(blf_path) as log:
            for frame in log:
                #print(frame)
                if effective_channels is not None and frame.channel not in effective_channels:
                    continue
                if start_time is not None and frame.timestamp < start_time:
                    continue
                if end_time is not None and frame.timestamp > end_time:
                    continue
                id29 = frame.arbitration_id & 0x1FFFFFFF # 811
                entries = id_to_entries.get(id29)
                if not entries:
                    continue

                data_bytes = bytes(frame.data)
                for bus, msg_def, sig_name, key in entries:
                    # 若 bus 配置了通道映射，则确保匹配
                    bus_chan = self.bus_to_channel.get(bus)
                    if effective_channels is not None and bus_chan is not None and frame.channel != bus_chan:
                        continue
                    try:
                        decoded = msg_def.decode(
                            data_bytes,
                            decode_choices=self.decode_choices,
                            scaling=self.scaling,
                        )
                    except Exception:
                        continue
                    if sig_name not in decoded:
                        continue
                    val = decoded[sig_name]
                    if isinstance(val, (int, bool)):
                        valf = float(val)
                    elif isinstance(val, float):
                        valf = val
                    else:
                        raise TypeError(f"{key} 解码得到非数值: {type(val).__name__}")
                    grouped.setdefault(key, []).append((float(frame.timestamp), valf))

        # 4) 排序
        for series in grouped.values():
            series.sort(key=lambda x: x[0])

        # 5) 归一化 + 单位 + 保留小数
        if time_origin not in ("keep", "global_min"):
            raise ValueError("time_origin 仅支持 'keep' 或 'global_min'")
        if time_unit not in ("s", "ms", "us"):
            raise ValueError("time_unit 仅支持 's' | 'ms' | 'us'")

        global_min = (
            min((ts for series in grouped.values() for ts, _ in series), default=0.0)
            if time_origin == "global_min"
            else 0.0
        )
        factor = 1.0 if time_unit == "s" else (1e3 if time_unit == "ms" else 1e6)

        for key, series in grouped.items():
            grouped[key] = [(round((ts - global_min) * factor, time_decimals), v) for ts, v in series]

        return grouped
        
if __name__ == "__main__":
    extractor = BLFSignalExtractor(
        dbc_paths={"CAN 1": "D:\\Test\\Automation\\case_handler\\config_file\\xxx.dbc", "CAN 2": "D:\\Test\\Automation\\case_handler\\config_file\\xxxx.dbc"},
        decode_choices=False,
        scaling=True,
        bus_name_to_channel={"CAN 1": 0, "CAN 2": 1},  # 可选：若需要按通道过滤自动匹配
    )

    tokens = [
        #"CAN 1::Media_0x32B::CSW_Enable_S",
        # "CAN 1::ADC_0x29C::CSW_Stats_S",
        "CAN 1::Left_BCM_0x151::Speed_Signal_151_S",
        #"CAN 2::IPB_0x147::IPB_TAB_State_S",
    ]

    series = extractor.collect_grouped_series_by_tokens(
        blf_path="D:\\Test\\Automation\\can_trace\\TC-001_20250930_181714.blf",
        tokens=tokens,
        time_origin="global_min",  # 或 "keep"
        time_unit="s",             # 你需要秒
        time_decimals=6,           # 保留6位小数
    )
    print(series)
