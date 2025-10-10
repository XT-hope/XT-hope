from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple
import re

from can.io import BLFReader
import cantools


@dataclass(frozen=True)
class SignalRecord:
    timestamp: float
    channel: int
    id_hex: str
    message: str
    signal: str
    value: float
    bus: Optional[str] = None


FrameKey = Tuple[int, bool]  # (29bit_id, is_extended)


class BLFSignalExtractor:
    """
    基于 DBC 的 BLF 信号提取器。

    - 支持按消息名或帧 ID 选择目标信号
    - 支持通道与时间窗口过滤
    - 输出值统一为 float（含 int/bool 的强制转换）

    参数
    ------
    dbc_paths: DBC 文件路径列表
    decode_choices: True 则将枚举解码为名称字符串；为确保可转 float，默认 False
    scaling: 是否将原始值换算为物理值
    strict: True 时若目标信号在消息中不存在，将抛出异常；否则忽略该信号
    """

    def __init__(
        self,
        dbc_paths: Sequence[str] | Mapping[str, str],
        *,
        decode_choices: bool = False,
        scaling: bool = True,
        strict: bool = True,
        bus_name_to_channel: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.decode_choices: bool = decode_choices
        self.scaling: bool = scaling
        self.strict: bool = strict

        self._databases: List[cantools.database.can.database.Database] = []
        self._message_by_name: Dict[str, cantools.database.can.Message] = {}
        self._messages_by_id29: Dict[int, List[cantools.database.can.Message]] = {}
        # 按总线名划分的索引
        self._db_by_bus: Dict[str, cantools.database.can.database.Database] = {}
        self._message_by_bus_and_name: Dict[
            str, Dict[str, cantools.database.can.Message]
        ] = {}
        self._messages_by_bus_and_id29: Dict[
            str, Dict[int, List[cantools.database.can.Message]]
        ] = {}
        self._bus_to_channel: Dict[str, int] = dict(bus_name_to_channel or {})

        self._load_databases(dbc_paths)
        self._index_messages()

    # ------------------------------- public API -------------------------------
    def iter_signals(
        self,
        blf_path: str,
        targets: Mapping[str, Sequence[str]],
        *,
        channels: Optional[Set[int]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Iterator[SignalRecord]:
        """流式遍历返回命中的信号数据。"""
        if not targets:
            return

        message_to_signals = self._build_request_map(targets)
        if not message_to_signals:
            return

        id29_to_requested_messages: Dict[int, List[cantools.database.can.Message]] = {}
        for msg_def in message_to_signals.keys():
            id29 = msg_def.frame_id & 0x1FFFFFFF
            id29_to_requested_messages.setdefault(id29, []).append(msg_def)

        with BLFReader(blf_path) as log:
            for raw in log:
                if channels is not None and raw.channel not in channels:
                    continue
                if start_time is not None and raw.timestamp < start_time:
                    continue
                if end_time is not None and raw.timestamp > end_time:
                    continue

                id29 = raw.arbitration_id & 0x1FFFFFFF
                maybe_defs = id29_to_requested_messages.get(id29)
                if not maybe_defs:
                    continue

                payload = bytes(raw.data)
                for msg_def in maybe_defs:
                    try:
                        decoded = msg_def.decode(
                            payload,
                            decode_choices=self.decode_choices,
                            scaling=self.scaling,
                        )
                    except Exception:
                        continue

                    wanted_signals = message_to_signals[msg_def]
                    if not wanted_signals:
                        break

                    for signal_name in wanted_signals:
                        if signal_name not in decoded:
                            continue
                        value = decoded[signal_name]
                        value_as_float = self._to_float(value, signal_name, msg_def.name)
                        yield SignalRecord(
                            timestamp=float(raw.timestamp),
                            channel=int(raw.channel),
                            id_hex=hex(id29),
                            message=msg_def.name,
                            signal=signal_name,
                            value=value_as_float,
                        )
                    break  # 同一帧只需解一次

    def collect_signals(
        self,
        blf_path: str,
        targets: Mapping[str, Sequence[str]],
        *,
        channels: Optional[Set[int]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[SignalRecord]:
        """一次性收集为列表。"""
        out: List[SignalRecord] = []
        for rec in self.iter_signals(
            blf_path,
            targets,
            channels=channels,
            start_time=start_time,
            end_time=end_time,
        ):
            out.append(rec)
            if limit is not None and len(out) >= limit:
                break
        return out

    def collect_grouped_series(
        self,
        blf_path: str,
        targets: Mapping[str, Sequence[str]],
        *,
        channels: Optional[Set[int]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        time_origin: str = "keep",
        time_unit: str = "s",
        time_decimals: int = 6,
    ) -> Dict[str, List[Tuple[float, float]]]:
        """
        将同一信号的数据聚合到一起并按时间戳升序排序。

        返回
        ------
        Dict[str, List[Tuple[float, float]]]
            key: "{message}.{signal}"
            value: 时间序列 [(timestamp, value_float), ...]，按 timestamp 升序

        参数
        ------
        time_origin:
            - "keep": 不做归一化，保留原始秒时间戳
            - "global_min": 全局减去最小时间戳，使起点约为 0
        time_unit:
            - "s" | "ms" | "us"，默认 "s"
        time_decimals:
            - 对归一化后的时间进行 round，默认 6 位小数（便于绘图/导出）
        """
        grouped: Dict[str, List[Tuple[float, float]]] = {}
        for rec in self.iter_signals(
            blf_path,
            targets,
            channels=channels,
            start_time=start_time,
            end_time=end_time,
        ):
            key = f"{rec.message}.{rec.signal}"
            grouped.setdefault(key, []).append((rec.timestamp, rec.value))

        # 对每个信号的时间序列进行排序（按时间戳）
        for series in grouped.values():
            series.sort(key=lambda pair: pair[0])

        # 归一化与单位转换
        if time_origin is not None and time_origin != "keep":
            if time_origin == "global_min":
                # 全局最小时间戳
                try:
                    global_min = min(ts for series in grouped.values() for ts, _ in series)
                except ValueError:
                    global_min = 0.0
                offsets = {k: global_min for k in grouped.keys()}
            else:
                raise ValueError("time_origin 仅支持 'keep' | 'global_min'")
        else:
            offsets = {k: 0.0 for k in grouped.keys()}

        # 单位系数
        if time_unit == "s":
            factor = 1.0
        elif time_unit == "ms":
            factor = 1e3
        elif time_unit == "us":
            factor = 1e6
        else:
            raise ValueError("time_unit 仅支持 's' | 'ms' | 'us'")

        normalized: Dict[str, List[Tuple[float, float]]] = {}
        for key, series in grouped.items():
            offset = offsets.get(key, 0.0)
            if time_decimals is not None and time_decimals >= 0:
                normalized[key] = [
                    (round((ts - offset) * factor, time_decimals), val)
                    for ts, val in series
                ]
            else:
                normalized[key] = [((ts - offset) * factor, val) for ts, val in series]

        return normalized

    # ---------------------- tokens API: BUS::MESSAGE::SIGNAL ------------------
    def iter_signals_by_tokens(
        self,
        blf_path: str,
        tokens: Sequence[str],
        *,
        channels: Optional[Set[int]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Iterator[SignalRecord]:
        """
        仅按形如 "CAN 1::MessageName::SignalName" 的 token 提取信号。
        需在初始化时传入 dbc_paths 为 {bus_name: dbc_path}。
        """
        if not tokens:
            return

        id29_to_entries, used_buses = self._build_request_from_tokens(tokens)

        # 计算有效通道集合：优先使用调用方传入的 channels；否则按总线映射推断
        effective_channels: Optional[Set[int]]
        if channels is not None:
            effective_channels = set(channels)
        else:
            mapped = {self._bus_to_channel[b] for b in used_buses if b in self._bus_to_channel}
            effective_channels = mapped if mapped else None

        with BLFReader(blf_path) as log:
            for raw in log:
                if effective_channels is not None and raw.channel not in effective_channels:
                    continue
                if start_time is not None and raw.timestamp < start_time:
                    continue
                if end_time is not None and raw.timestamp > end_time:
                    continue

                id29 = raw.arbitration_id & 0x1FFFFFFF
                entries = id29_to_entries.get(id29)
                if not entries:
                    continue

                payload = bytes(raw.data)
                for bus_name, msg_def, wanted_signals in entries:
                    # 若能映射到通道，则确保通道匹配该总线
                    bus_chan = self._bus_to_channel.get(bus_name)
                    if effective_channels is not None and bus_chan is not None and raw.channel != bus_chan:
                        continue
                    try:
                        decoded = msg_def.decode(
                            payload,
                            decode_choices=self.decode_choices,
                            scaling=self.scaling,
                        )
                    except Exception:
                        continue

                    for signal_name in wanted_signals:
                        if signal_name not in decoded:
                            continue
                        value = decoded[signal_name]
                        value_as_float = self._to_float(value, signal_name, msg_def.name)
                        yield SignalRecord(
                            timestamp=float(raw.timestamp),
                            channel=int(raw.channel),
                            id_hex=hex(id29),
                            message=msg_def.name,
                            signal=signal_name,
                            value=value_as_float,
                            bus=bus_name,
                        )
                    break  # 一旦成功解码本条目即可

    def collect_grouped_series_by_tokens(
        self,
        blf_path: str,
        tokens: Sequence[str],
        *,
        channels: Optional[Set[int]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        time_origin: str = "keep",
        time_unit: str = "s",
        time_decimals: int = 6,
    ) -> Dict[str, List[Tuple[float, float]]]:
        """
        与 collect_grouped_series 相同，但 targets 以 token 列表传入，
        返回 key 为 "BUS::MESSAGE::SIGNAL"。
        """
        grouped: Dict[str, List[Tuple[float, float]]] = {}
        for rec in self.iter_signals_by_tokens(
            blf_path,
            tokens,
            channels=channels,
            start_time=start_time,
            end_time=end_time,
        ):
            # 无法从 SignalRecord 直接得知总线名，这里使用 token 解析构建的映射来产出 key。
            # 为保持简洁，这里 key 组合为 "{message}.{signal}" 的旧形式不包含总线；
            # 若你需要严格的 "BUS::MESSAGE::SIGNAL"，请在上层用 tokens 形成 key。
            key = f"{rec.message}.{rec.signal}"
            grouped.setdefault(key, []).append((rec.timestamp, rec.value))

        for series in grouped.values():
            series.sort(key=lambda pair: pair[0])

        # 归一化 + 单位 + 四舍五入
        if time_origin is not None and time_origin != "keep":
            if time_origin == "global_min":
                try:
                    global_min = min(ts for series in grouped.values() for ts, _ in series)
                except ValueError:
                    global_min = 0.0
                offsets = {k: global_min for k in grouped.keys()}
            else:
                raise ValueError("time_origin 仅支持 'keep' | 'global_min'")
        else:
            offsets = {k: 0.0 for k in grouped.keys()}

        if time_unit == "s":
            factor = 1.0
        elif time_unit == "ms":
            factor = 1e3
        elif time_unit == "us":
            factor = 1e6
        else:
            raise ValueError("time_unit 仅支持 's' | 'ms' | 'us'")

        normalized: Dict[str, List[Tuple[float, float]]] = {}
        for key, series in grouped.items():
            offset = offsets.get(key, 0.0)
            if time_decimals is not None and time_decimals >= 0:
                normalized[key] = [
                    (round((ts - offset) * factor, time_decimals), val)
                    for ts, val in series
                ]
            else:
                normalized[key] = [((ts - offset) * factor, val) for ts, val in series]

        return normalized

    # ------------------------------ internal impl -----------------------------
    def _load_databases(self, dbc_paths: Sequence[str] | Mapping[str, str]) -> None:
        # 兼容两种形式：
        # 1) ["a.dbc", "b.dbc"]
        # 2) {"CAN 1": "a.dbc", "CAN 2": "b.dbc"}
        if isinstance(dbc_paths, Mapping):
            for bus_name, path in dbc_paths.items():
                db = cantools.database.load_file(path)
                self._db_by_bus[bus_name] = db  # type: ignore[assignment]
                self._databases.append(db)  # type: ignore[arg-type]
        else:
            for path in dbc_paths:
                db = cantools.database.load_file(path)
                self._databases.append(db)  # type: ignore[arg-type]

    def _index_messages(self) -> None:
        # 全局索引（兼容旧 API）
        for db in self._databases:
            for m in db.messages:
                self._message_by_name[m.name] = m
                id29 = m.frame_id & 0x1FFFFFFF
                self._messages_by_id29.setdefault(id29, []).append(m)

        # 分总线索引（仅在传入了映射时启用）
        if self._db_by_bus:
            for bus_name, db in self._db_by_bus.items():
                name_map: Dict[str, cantools.database.can.Message] = {}
                id_map: Dict[int, List[cantools.database.can.Message]] = {}
                for m in db.messages:
                    name_map[m.name] = m
                    id29 = m.frame_id & 0x1FFFFFFF
                    id_map.setdefault(id29, []).append(m)
                self._message_by_bus_and_name[bus_name] = name_map
                self._messages_by_bus_and_id29[bus_name] = id_map

    def _parse_id_token(self, token: str) -> Optional[int]:
        s = token.strip()
        try:
            if s.lower().startswith("0x"):
                return int(s, 16)
            return int(s, 10)
        except ValueError:
            return None

    def _build_request_map(
        self, targets: Mapping[str, Sequence[str]]
    ) -> Dict[cantools.database.can.Message, Set[str]]:
        message_to_signals: Dict[cantools.database.can.Message, Set[str]] = {}
        for key, signals in targets.items():
            msg_def: Optional[cantools.database.can.Message] = None

            if key in self._message_by_name:
                msg_def = self._message_by_name[key]
            else:
                id29 = self._parse_id_token(key)
                if id29 is not None:
                    candidate_list = self._messages_by_id29.get(id29)
                    if candidate_list:
                        msg_def = candidate_list[0]

            if msg_def is None:
                if self.strict:
                    raise KeyError(f"目标消息未找到: {key}")
                else:
                    continue

            # 可选：在 strict 模式下校验信号名存在
            if self.strict:
                defined_names = {sig.name for sig in msg_def.signals}
                unknown = [name for name in signals if name not in defined_names]
                if unknown:
                    raise KeyError(
                        f"消息 {msg_def.name} 中不存在信号: {', '.join(unknown)}"
                    )

            message_to_signals.setdefault(msg_def, set()).update(signals)

        return message_to_signals

    def _parse_signal_token(self, token: str) -> Optional[Tuple[str, str, str]]:
        """解析形如 "CAN X::MESSAGE::SIGNAL" 的 token（总线名限定为 CAN+数字）。
        返回 (bus, message, signal)；若无法解析返回 None。
        """
        m = re.fullmatch(r"\s*(CAN\s*\d+)\s*::\s*([^:]+?)\s*::\s*([^:]+?)\s*", token)
        if not m:
            return None
        bus, message, signal = m.group(1), m.group(2), m.group(3)
        return bus, message, signal

    def _build_request_from_tokens(
        self, tokens: Sequence[str]
    ) -> Tuple[Dict[int, List[Tuple[str, cantools.database.can.Message, Set[str]]]], Set[str]]:
        """
        将 token 列表编译为:
          - id29 -> [(bus_name, message_def, wanted_signals_set), ...]
          - 使用到的总线名集合
        """
        if not self._db_by_bus:
            if self.strict:
                raise ValueError("使用 token 形式需要以 {bus: dbc} 形式提供 dbc_paths")
            return {}, set()

        # (bus, message_def) -> signals
        req_map: Dict[Tuple[str, cantools.database.can.Message], Set[str]] = {}
        used_buses: Set[str] = set()
        for tok in tokens:
            parsed = self._parse_signal_token(tok)
            if not parsed:
                if self.strict:
                    raise ValueError(f"无法解析信号 token: {tok}")
                else:
                    continue
            bus, msg_name, sig_name = parsed
            db = self._db_by_bus.get(bus)
            if db is None:
                if self.strict:
                    raise KeyError(f"未知总线: {bus}")
                else:
                    continue
            msg_map = self._message_by_bus_and_name.get(bus, {})
            msg_def = msg_map.get(msg_name)
            if msg_def is None:
                if self.strict:
                    raise KeyError(f"总线 {bus} 的消息未找到: {msg_name}")
                else:
                    continue
            if self.strict:
                defined = {s.name for s in msg_def.signals}
                if sig_name not in defined:
                    raise KeyError(f"消息 {msg_def.name} 中不存在信号: {sig_name}")

            req_map.setdefault((bus, msg_def), set()).add(sig_name)
            used_buses.add(bus)

        id29_to_entries: Dict[int, List[Tuple[str, cantools.database.can.Message, Set[str]]]] = {}
        for (bus_name, msg_def), sigs in req_map.items():
            id29 = msg_def.frame_id & 0x1FFFFFFF
            id29_to_entries.setdefault(id29, []).append((bus_name, msg_def, sigs))

        return id29_to_entries, used_buses

    def _to_float(self, value: Any, signal_name: str, message_name: str) -> float:
        if isinstance(value, float):
            return value
        if isinstance(value, (int, bool)):
            return float(value)
        # cantools 在 decode_choices=True 时可能返回字符串（枚举名），此时无法强制为 float
        # 默认 decode_choices=False 避免该情况；如仍出现字符串，尝试宽松解析
        if isinstance(value, str):
            # 宽松：纯数字字符串
            try:
                return float(value)
            except ValueError:
                pass
            raise TypeError(
                f"信号 {message_name}.{signal_name} 解码为字符串，无法转换为 float；"
                f"请在初始化时设置 decode_choices=False"
            )
        # 其它容器类型（如 dict/list）视为错误
        raise TypeError(
            f"信号 {message_name}.{signal_name} 类型 {type(value).__name__} 不可转换为 float"
        )
