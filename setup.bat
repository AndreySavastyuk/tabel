@echo off
cd /d "%~dp0"
echo ============================================
echo   Tabel SKUD - first-time machine setup
echo ============================================
echo.

where python >nul 2>&1 || (echo [ERROR] Python not found in PATH. Install Python 3.11+ and retry. & pause & exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] Node/npm not found in PATH. Install Node.js LTS and retry. & pause & exit /b 1)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating Python venv...
  python -m venv .venv || (echo [ERROR] venv creation failed. & pause & exit /b 1)
)

echo [2/4] Installing Python dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || (echo [ERROR] pip install failed. & pause & exit /b 1)

echo [3/4] Installing web dependencies (npm ci)...
pushd web
call npm ci
popd

echo [4/4] Applying DB migrations (creates tabel.db if missing)...
.venv\Scripts\python.exe -m alembic upgrade head || (echo [ERROR] alembic failed. & pause & exit /b 1)

echo.
echo ============================================
echo   Setup complete. Start the app with: run.bat
echo ============================================
echo.
echo NOTE: SKUD data and tabel.db (personal data) are NOT in git.
echo  - To carry real users/data between machines: copy tabel.db into this folder.
echo  - Or place source SKUD files and run:  .venv\Scripts\python.exe -m scripts.seed_from_excel
echo    (see CLAUDE.md for details)
pause
