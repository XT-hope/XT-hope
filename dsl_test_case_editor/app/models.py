from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FileEntry(BaseModel):
    file_name: str
    file_type: str
    original_name: str
    uploaded_at: str


class ProjectInfo(BaseModel):
    project_id: str
    name: str
    description: Optional[str] = None
    created_at: str
    updated_at: str


class ProjectConfig(ProjectInfo):
    dbc_files: List[FileEntry] = Field(default_factory=list)
    system_variable_files: List[FileEntry] = Field(default_factory=list)


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UploadResponse(BaseModel):
    file_name: str
    file_type: str


class MappingRequest(BaseModel):
    mapping: Dict[str, int]


class SaveCaseRequest(BaseModel):
    content: str
    save_to_oss: bool = False


class ValidateRequest(BaseModel):
    project_id: str
    content: str


class Diagnostic(BaseModel):
    line: int
    severity: str
    message: str


class ValidateResponse(BaseModel):
    diagnostics: List[Diagnostic]


class SuggestionResponse(BaseModel):
    suggestions: List[str]


class AiAskRequest(BaseModel):
    project_id: str
    question: str
    context: Optional[str] = None


class AiAskResponse(BaseModel):
    answer: str
