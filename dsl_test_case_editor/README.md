# DSL Test Case Editor (Web)

This project provides a lightweight web-based editor for DSL test cases.
It supports project management, DBC uploads, CAN channel mapping, signal
and variable suggestions, DSL validation, and local case storage. AI Q&A
and DBC-to-environment-DBC conversion are included as extensible stubs.

## Features
- Create/open projects with a fixed folder layout
- Upload vehicle DBC files and environment variable DBC files
- Upload CANoe system variable files for sys:: suggestions
- Map vehicle DBC files to CAN channels (required)
- Query suggestions for sig/env/sys targets
- Validate DSL syntax and references
- Save DSL cases locally; optional OSS stub
- Reserved interface for DBC -> environment DBC conversion

## Run
```bash
python3 -m uvicorn dsl_test_case_editor.app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000 in a browser.

## Data Directory
Runtime data is stored under:
```
dsl_test_case_editor_data/
  projects/
    <project_id>/
      dbc_file/
      mapping_file/
      system_variable/
      dsl_case/
```

## AI Integration (Stub)
By default, the AI endpoint returns a placeholder response. You can
replace the provider in `ai_service.py` or wire it to your internal
endpoint.
