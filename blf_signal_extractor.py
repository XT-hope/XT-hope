from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

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
        dbc_paths: Sequence[str],
        *,
        decode_choices: bool = False,
        scaling: bool = True,
        strict: bool = True,
    ) -> None:
        self.decode_choices: bool = decode_choices
        self.scaling: bool = scaling
        self.strict: bool = strict

        self._databases: List[cantools.database.can.database.Database] = []
        self._message_by_name: Dict[str, cantools.database.can.Message] = {}
        self._messages_by_id29: Dict[int, List[cantools.database.can.Message]] = {}

        self._load_databases(list(dbc_paths))
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
    ) -> Dict[str, List[Tuple[float, float]]]:
        """
        将同一信号的数据聚合到一起并按时间戳升序排序。

        返回
        ------
        Dict[str, List[Tuple[float, float]]]
            key: "{message}.{signal}"
            value: 时间序列 [(timestamp, value_float), ...]，按 timestamp 升序
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

        return grouped

    # ------------------------------ internal impl -----------------------------
    def _load_databases(self, dbc_paths: List[str]) -> None:
        for path in dbc_paths:
            db = cantools.database.load_file(path)
            # cantools 的 Database 类型别名层级较多，这里保持运行时检查
            self._databases.append(db)  # type: ignore[arg-type]

    def _index_messages(self) -> None:
        for db in self._databases:
            for m in db.messages:
                self._message_by_name[m.name] = m
                id29 = m.frame_id & 0x1FFFFFFF
                self._messages_by_id29.setdefault(id29, []).append(m)

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
