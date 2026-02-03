from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .ai_service import build_ai_provider
from .config import PROJECTS_DIR, ensure_data_dirs
from .dsl_parser import validate_dsl
from .models import (
    AiAskRequest,
    AiAskResponse,
    CreateProjectRequest,
    MappingRequest,
    ProjectConfig,
    ProjectInfo,
    SaveCaseRequest,
    SuggestionResponse,
    UploadResponse,
    ValidateRequest,
    ValidateResponse,
)
from .storage import ProjectStorage
from .suggestions import ProjectIndexCache
from .utils import safe_join


ensure_data_dirs()

app = FastAPI(title="DSL Test Case Editor")
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parents[1] / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")

storage = ProjectStorage(PROJECTS_DIR)
index_cache = ProjectIndexCache()
ai_provider = build_ai_provider()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/projects", response_model=List[ProjectInfo])
def list_projects() -> List[ProjectInfo]:
    return storage.list_projects()


@app.post("/api/projects", response_model=ProjectConfig)
def create_project(payload: CreateProjectRequest) -> ProjectConfig:
    return storage.create_project(payload.name, payload.description)


@app.get("/api/projects/{project_id}", response_model=ProjectConfig)
def get_project(project_id: str) -> ProjectConfig:
    _ensure_project(project_id)
    return storage.get_project_config(project_id)


@app.get("/api/projects/{project_id}/mapping")
def get_mapping(project_id: str) -> dict:
    _ensure_project(project_id)
    return {"mapping": storage.get_mapping(project_id)}


@app.put("/api/projects/{project_id}/mapping")
def save_mapping(project_id: str, payload: MappingRequest) -> dict:
    _ensure_project(project_id)
    storage.save_mapping(project_id, payload.mapping)
    return {"status": "ok"}


@app.post("/api/projects/{project_id}/upload", response_model=UploadResponse)
async def upload_file(
    project_id: str,
    file_type: str = Form(...),
    file: UploadFile = File(...),
) -> UploadResponse:
    _ensure_project(project_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload.")
    try:
        file_name, entry_type = storage.save_upload(
            project_id, file.filename or "upload.bin", content, file_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadResponse(file_name=file_name, file_type=entry_type)


@app.get("/api/projects/{project_id}/cases")
def list_cases(project_id: str) -> dict:
    _ensure_project(project_id)
    return {"cases": storage.list_cases(project_id)}


@app.get("/api/projects/{project_id}/cases/{case_name}")
def read_case(project_id: str, case_name: str) -> dict:
    _ensure_project(project_id)
    try:
        content = storage.read_case(project_id, case_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found.") from exc
    return {"content": content}


@app.post("/api/projects/{project_id}/cases/{case_name}")
def save_case(project_id: str, case_name: str, payload: SaveCaseRequest) -> dict:
    _ensure_project(project_id)
    message = storage.save_case(
        project_id, case_name, payload.content, payload.save_to_oss
    )
    return {"status": "ok", "message": message}


@app.post("/api/validate", response_model=ValidateResponse)
def validate(payload: ValidateRequest) -> ValidateResponse:
    _ensure_project(payload.project_id)
    mapping = storage.get_mapping(payload.project_id)
    diagnostics = validate_dsl(payload.content, mapping)
    return ValidateResponse(diagnostics=diagnostics)


@app.get("/api/suggestions", response_model=SuggestionResponse)
def get_suggestions(
    project_id: str = Query(...),
    suggestion_type: str = Query(..., alias="type"),
    query: str = Query("", alias="q"),
    limit: int = Query(50, ge=1, le=200),
) -> SuggestionResponse:
    _ensure_project(project_id)
    config = storage.get_project_config(project_id)
    mapping = storage.get_mapping(project_id)
    project_dir = safe_join(PROJECTS_DIR, project_id)
    index = index_cache.get_index(project_id, project_dir, config, mapping)
    query_lower = query.lower()
    if suggestion_type == "sig":
        source = index.sig_targets
    elif suggestion_type == "env":
        source = index.env_targets
    elif suggestion_type == "sys":
        source = index.sys_targets
    else:
        raise HTTPException(status_code=400, detail="Unknown suggestion type.")
    results = [item for item in source if query_lower in item.lower()]
    return SuggestionResponse(suggestions=results[:limit])


@app.post("/api/ai/ask", response_model=AiAskResponse)
def ask_ai(payload: AiAskRequest) -> AiAskResponse:
    _ensure_project(payload.project_id)
    answer = ai_provider.ask(payload.question, payload.context)
    return AiAskResponse(answer=answer)


@app.post("/api/projects/{project_id}/convert-env-dbc")
def convert_env_dbc(project_id: str) -> dict:
    _ensure_project(project_id)
    return {
        "status": "not_implemented",
        "message": "Conversion is not implemented yet.",
    }


def _ensure_project(project_id: str) -> None:
    try:
        project_dir = safe_join(PROJECTS_DIR, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found.")
