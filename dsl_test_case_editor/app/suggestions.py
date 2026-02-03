import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import cantools

from .models import ProjectConfig


@dataclass
class SuggestionIndex:
    sig_targets: List[str]
    env_targets: List[str]
    sys_targets: List[str]


@dataclass
class _CacheEntry:
    mtime: float
    index: SuggestionIndex


class ProjectIndexCache:
    def __init__(self) -> None:
        self._cache: Dict[str, _CacheEntry] = {}

    def get_index(
        self,
        project_id: str,
        project_dir: Path,
        config: ProjectConfig,
        mapping: Dict[str, int],
    ) -> SuggestionIndex:
        latest_mtime = _latest_mtime(project_dir, config)
        entry = self._cache.get(project_id)
        if entry and entry.mtime >= latest_mtime:
            return entry.index
        index = build_index(project_dir, config, mapping)
        self._cache[project_id] = _CacheEntry(mtime=latest_mtime, index=index)
        return index


def _latest_mtime(project_dir: Path, config: ProjectConfig) -> float:
    files: List[Path] = []
    for entry in config.dbc_files:
        files.append(project_dir / "dbc_file" / entry.file_name)
    for entry in config.system_variable_files:
        files.append(project_dir / "system_variable" / entry.file_name)
    files.append(project_dir / "mapping_file" / "mapping.json")
    mtimes = [p.stat().st_mtime for p in files if p.exists()]
    return max(mtimes) if mtimes else 0.0


def build_index(
    project_dir: Path,
    config: ProjectConfig,
    mapping: Dict[str, int],
) -> SuggestionIndex:
    sig_targets: Set[str] = set()
    env_targets: Set[str] = set()
    sys_targets: Set[str] = set()

    dbc_dir = project_dir / "dbc_file"
    for entry in config.dbc_files:
        dbc_path = dbc_dir / entry.file_name
        if not dbc_path.exists():
            continue
        channel = mapping.get(entry.file_name)
        if channel is None:
            continue
        for message_name, signal_name in _load_dbc_signals(dbc_path):
            if entry.file_type == "env":
                env_targets.add(f"env::CAN {channel}::{message_name}::{signal_name}")
                friendly = _try_env_friendly_name(signal_name, channel)
                if friendly:
                    env_targets.add(friendly)
            else:
                sig_targets.add(f"sig::CAN {channel}::{message_name}::{signal_name}")

    sys_dir = project_dir / "system_variable"
    for entry in config.system_variable_files:
        path = sys_dir / entry.file_name
        if not path.exists():
            continue
        sys_targets.update(_load_system_variables(path))

    return SuggestionIndex(
        sig_targets=sorted(sig_targets),
        env_targets=sorted(env_targets),
        sys_targets=sorted(sys_targets),
    )


def _load_dbc_signals(path: Path) -> Iterable[Tuple[str, str]]:
    db = cantools.database.load_file(str(path))
    for message in db.messages:
        for signal in message.signals:
            yield message.name, signal.name


_SYS_TOKEN_RE = re.compile(r"(?:sys::)?[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)+")


def _load_system_variables(path: Path) -> Set[str]:
    if path.suffix.lower() in {".xml", ".vsys"}:
        from xml.etree import ElementTree

        try:
            root = ElementTree.parse(path).getroot()
            return _extract_sys_from_xml(root)
        except Exception:
            pass
    return _extract_sys_from_text(path)


def _extract_sys_from_xml(root) -> Set[str]:
    names: Set[str] = set()
    for elem in root.iter():
        for key in ("name", "Name"):
            value = elem.attrib.get(key)
            if not value:
                continue
            names.add(_normalize_sys_name(value))
    return {name for name in names if name}


def _extract_sys_from_text(path: Path) -> Set[str]:
    names: Set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        for token in _SYS_TOKEN_RE.findall(line):
            names.add(_normalize_sys_name(token))
    return {name for name in names if name}


def _normalize_sys_name(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("sys::"):
        return value
    if "::" in value:
        return f"sys::{value}"
    return ""


_ENV_SIGNAL_RE = re.compile(r"^E_.+_(Pv|Rv|Vt)$")


def _try_env_friendly_name(signal_name: str, channel: int) -> Optional[str]:
    if not _ENV_SIGNAL_RE.match(signal_name):
        return None
    base = signal_name[:-3]
    parts = base.split("_")
    hex_index = None
    for index, part in enumerate(parts):
        if part.startswith("0x") and len(part) > 2:
            hex_index = index
            break
    if hex_index is None or hex_index == 0 or hex_index >= len(parts) - 1:
        return None
    message = f"{parts[hex_index - 1]}_{parts[hex_index]}"
    signal = "_".join(parts[hex_index + 1 :])
    if not signal:
        return None
    return f"env::CAN {channel}::{message}::{signal}"
