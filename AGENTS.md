# ProcuraVagas / Observable Job Agent — Project Rules & Execution Guidelines

## System & Execution Context (Windows 10/11)
- **Terminal:** PowerShell 7+ (`pwsh`).
- **Anti-Hanging Protocol:** Always use flat execution without outer quotes for single commands: `pwsh -c <command>`.

## Authorized Executables & Commands (Allow List)
- **Package Management:**
  - `pwsh -c uv --version`
  - `pwsh -c uv sync --all-groups`
  - `pwsh -c uv pip install <pkg>`
- **Python Execution:**
  - `pwsh -c .venv\Scripts\python.exe <script>`
- **Testing & Quality Checks:**
  - `pwsh -c .venv\Scripts\pytest.exe`
  - `pwsh -c .venv\Scripts\pytest.exe <path>`
  - `pwsh -c .venv\Scripts\pytest.exe gates/`
- **Linting & Formatting:**
  - `pwsh -c .venv\Scripts\ruff.exe check src/ tests/`
  - `pwsh -c .venv\Scripts\ruff.exe format src/ tests/`
- **Git Operations (3-Step Commit Protocol):**
  - Step 1: `pwsh -c git add -u` (and `pwsh -c git add <untracked_files>`)
  - Step 2: `cmd /c git commit -m "feat/fix: description"`
  - Step 3: `pwsh -c git push`
