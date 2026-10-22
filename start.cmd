@echo off
setlocal
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required. See START_WINDOWS.md.
  exit /b 1
)
uv run --no-project --python 3.12 python "%~dp0scripts\dev.py" %*
exit /b %errorlevel%
