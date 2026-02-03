from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "dsl_test_case_editor_data"
PROJECTS_DIR = DATA_DIR / "projects"
DEFAULT_ENCODING = "utf-8"


def ensure_data_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
