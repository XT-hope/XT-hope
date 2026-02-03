import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import DEFAULT_ENCODING
from .models import FileEntry, ProjectConfig, ProjectInfo
from .utils import safe_join, slugify, utc_timestamp


class OssPublisher:
    def publish(self, project_id: str, case_name: str, content: str) -> str:
        del project_id, case_name, content
        return "OSS is not configured yet."


class ProjectStorage:
    def __init__(self, projects_dir: Path) -> None:
        self.projects_dir = projects_dir
        self.oss_publisher = OssPublisher()

    def _project_dir(self, project_id: str) -> Path:
        return safe_join(self.projects_dir, project_id)

    def _project_file(self, project_id: str) -> Path:
        return safe_join(self._project_dir(project_id), "project.json")

    def _mapping_file(self, project_id: str) -> Path:
        return safe_join(self._project_dir(project_id), "mapping_file", "mapping.json")

    def _dbc_dir(self, project_id: str) -> Path:
        return safe_join(self._project_dir(project_id), "dbc_file")

    def _system_var_dir(self, project_id: str) -> Path:
        return safe_join(self._project_dir(project_id), "system_variable")

    def _case_dir(self, project_id: str) -> Path:
        return safe_join(self._project_dir(project_id), "dsl_case")

    def _init_project_dirs(self, project_dir: Path) -> None:
        (project_dir / "dbc_file").mkdir(parents=True, exist_ok=True)
        (project_dir / "mapping_file").mkdir(parents=True, exist_ok=True)
        (project_dir / "system_variable").mkdir(parents=True, exist_ok=True)
        (project_dir / "dsl_case").mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding=DEFAULT_ENCODING))

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
            encoding=DEFAULT_ENCODING,
        )

    def _unique_project_id(self, base_id: str) -> str:
        if not self._project_dir(base_id).exists():
            return base_id
        index = 2
        while True:
            candidate = f"{base_id}-{index}"
            if not self._project_dir(candidate).exists():
                return candidate
            index += 1

    def create_project(self, name: str, description: Optional[str]) -> ProjectConfig:
        base_id = slugify(name)
        project_id = self._unique_project_id(base_id)
        project_dir = self._project_dir(project_id)
        self._init_project_dirs(project_dir)
        timestamp = utc_timestamp()
        config = ProjectConfig(
            project_id=project_id,
            name=name,
            description=description,
            created_at=timestamp,
            updated_at=timestamp,
            dbc_files=[],
            system_variable_files=[],
        )
        self._write_json(self._project_file(project_id), config.model_dump())
        self._write_json(self._mapping_file(project_id), {"version": 1, "mapping": {}})
        return config

    def list_projects(self) -> List[ProjectInfo]:
        projects: List[ProjectInfo] = []
        if not self.projects_dir.exists():
            return projects
        for entry in self.projects_dir.iterdir():
            if not entry.is_dir():
                continue
            config_path = entry / "project.json"
            if not config_path.exists():
                continue
            payload = self._read_json(config_path)
            try:
                projects.append(ProjectInfo(**payload))
            except Exception:
                continue
        return projects

    def get_project_config(self, project_id: str) -> ProjectConfig:
        payload = self._read_json(self._project_file(project_id))
        return ProjectConfig(**payload)

    def save_project_config(self, project_id: str, config: ProjectConfig) -> None:
        config.updated_at = utc_timestamp()
        self._write_json(self._project_file(project_id), config.model_dump())

    def get_mapping(self, project_id: str) -> Dict[str, int]:
        payload = self._read_json(self._mapping_file(project_id))
        mapping = payload.get("mapping", {})
        return {str(key): int(value) for key, value in mapping.items()}

    def save_mapping(self, project_id: str, mapping: Dict[str, int]) -> None:
        payload = {"version": 1, "mapping": mapping}
        self._write_json(self._mapping_file(project_id), payload)

    def _unique_name(self, directory: Path, filename: str) -> str:
        candidate = filename
        base = Path(filename).stem
        suffix = Path(filename).suffix
        index = 2
        while (directory / candidate).exists():
            candidate = f"{base}_{index}{suffix}"
            index += 1
        return candidate

    def save_upload(
        self,
        project_id: str,
        file_name: str,
        content: bytes,
        file_type: str,
    ) -> Tuple[str, str]:
        config = self.get_project_config(project_id)
        if file_type in ("vehicle_dbc", "env_dbc"):
            target_dir = self._dbc_dir(project_id)
        elif file_type == "system_variable":
            target_dir = self._system_var_dir(project_id)
        else:
            raise ValueError("Unsupported file type.")
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._unique_name(target_dir, file_name)
        target_path = safe_join(target_dir, safe_name)
        target_path.write_bytes(content)

        if file_type == "vehicle_dbc":
            entry_type = "vehicle"
        elif file_type == "env_dbc":
            entry_type = "env"
        else:
            entry_type = file_type
        entry = FileEntry(
            file_name=safe_name,
            file_type=entry_type,
            original_name=file_name,
            uploaded_at=utc_timestamp(),
        )
        if file_type == "system_variable":
            config.system_variable_files.append(entry)
        else:
            config.dbc_files.append(entry)
        self.save_project_config(project_id, config)
        return safe_name, entry_type

    def list_cases(self, project_id: str) -> List[str]:
        case_dir = self._case_dir(project_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        return sorted([p.name for p in case_dir.iterdir() if p.is_file()])

    def read_case(self, project_id: str, case_name: str) -> str:
        case_path = safe_join(self._case_dir(project_id), case_name)
        return case_path.read_text(encoding=DEFAULT_ENCODING)

    def save_case(
        self,
        project_id: str,
        case_name: str,
        content: str,
        save_to_oss: bool,
    ) -> str:
        case_dir = self._case_dir(project_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        target_path = safe_join(case_dir, case_name)
        target_path.write_text(content, encoding=DEFAULT_ENCODING)
        message = "Saved locally."
        if save_to_oss:
            message = self.oss_publisher.publish(project_id, case_name, content)
        return message
