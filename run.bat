@echo off
cd /d "%~dp0"

echo ==========================================
echo   Tabel SKUD
echo   API:   http://127.0.0.1:8000
echo   Web:   http://localhost:5173
echo   Login: admin / admin
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Create it: python -m venv .venv  and  .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
if not exist "web\node_modules" (
  echo [ERROR] web\node_modules not found. Run once: cd web ^&^& npm ci
  pause
  exit /b 1
)

echo [1/3] Applying DB migrations...
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 (
  echo [ERROR] Migration failed. See messages above.
  pause
  exit /b 1
)

echo [2/3] Starting API (port 8000) and Web (port 5173)...
start "Tabel API" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000"
start "Tabel Web" /D "%~dp0web" cmd /k "npm run dev"

echo [3/3] Opening browser...
timeout /t 6 /nobreak >nul
start "" http://localhost:5173

echo.
echo Two windows opened (Tabel API + Tabel Web). Close them to stop the servers.
