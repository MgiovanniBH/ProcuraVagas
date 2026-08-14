# ProcuraVagas / Observable Job Agent — Project Rules & Execution Guidelines

## System & Execution Context (Windows 10/11)
- **Terminal:** PowerShell 7+ (`pwsh`).
- **Anti-Hanging Protocol:** Always use flat execution without outer quotes for single commands: `pwsh -c <command>`.

## Authorized Executables & Commands (Allow List)
- **Package Management & Tooling:**
  - `pwsh -c uv --version`
  - `pwsh -c uv sync --all-groups`
  - `pwsh -c uv pip install <pkg>`
  - `pwsh -c npm --prefix web ci`
  - `pwsh -c npm --prefix web run build`
  - `pwsh -c npm --prefix web run dev`

- **Python Execution & Applications:**
  - `pwsh -c .venv\Scripts\python.exe <script>`
  - `pwsh -c .venv\Scripts\python.exe scripts/test_llm_live.py`
  - `pwsh -c .venv\Scripts\python.exe -m job_scout.app`
  - `pwsh -c .venv\Scripts\python.exe -m job_scout.api`
  - `pwsh -c .venv\Scripts\python.exe scripts/run_batch.py`
  - `pwsh -c .venv\Scripts\python.exe scripts/run_tailor_batch.py`

- **Testing, Quality & Evaluation:**
  - `pwsh -c .venv\Scripts\pytest.exe`
  - `pwsh -c .venv\Scripts\pytest.exe <path>`
  - `pwsh -c .venv\Scripts\pytest.exe gates/`
  - `pwsh -c .venv\Scripts\ruff.exe check src/ tests/ scripts/`
  - `pwsh -c .venv\Scripts\ruff.exe format src/ tests/ scripts/`

- **File System & Utility Checks:**
  - `pwsh -c Test-Path <path>`

- **Git Operations (3-Step Commit Protocol):**
  - Status/Log: `pwsh -c git status`, `pwsh -c git status -u`, `pwsh -c git log -n 5`
  - Step 1 (Flat auto-run): `pwsh -c git add -u` (and `pwsh -c git add <untracked_files>`)
  - Step 2 (CMD auto-run preserves quotes): `cmd /c git commit -m "feat/fix: description"`
  - Step 3 (Flat auto-run): `pwsh -c git push`
