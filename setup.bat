@echo off
setlocal
py -m venv .venv
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo.
echo Setup complete.
echo Start an OpenAI-compatible model server, then run run.bat and open http://localhost:8000
exit /b 0
:error
echo.
echo Setup failed. Check the error above.
exit /b 1
