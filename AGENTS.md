## Cursor Cloud specific instructions

### Project overview

BEV+GPS to OpenDRIVE (XODR) Converter — a pure-Python CLI tool with **zero external dependencies**. See `README.md` for full details.

### Running the application

```bash
python3 -m xodr_converter.cli \
  --gps data/example/gps.csv \
  --bev data/example/bev.json \
  --out out/example.xodr
```

A second dataset is available at `data/verify400/`.

### Linting

```bash
ruff check .                    # full repo (includes demo scripts)
ruff check xodr_converter/     # main package only
```

Existing lint warnings in the main package (`F841` unused variables in `stitch.py` and `xodr.py`) are pre-existing in the repo.

### Testing

No automated tests exist yet. Use `pytest` to run any tests added in the future:

```bash
pytest -v
```

### Key caveats

- `requirements.txt` is empty; the project relies entirely on the Python 3 standard library.
- `ruff` and `pytest` are installed as dev tools via `pip install --user` and live in `~/.local/bin`. Make sure `PATH` includes `$HOME/.local/bin`.
- Output directory (`out/`) is created automatically by the CLI if it does not exist.
