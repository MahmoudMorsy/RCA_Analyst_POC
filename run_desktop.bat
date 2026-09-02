@echo off
setlocal
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run_desktop.py
) else (
  py run_desktop.py
)
endlocal
