@echo off
echo ========================================================
echo Starting Incident Timeline Investigator (Full Stack)
echo ========================================================

echo Starting Backend on http://127.0.0.1:8000 ...
start "Incident Investigator - Backend (Port 8000)" cmd /k "cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo Starting Frontend on http://localhost:5173 ...
start "Incident Investigator - Frontend (Port 5173)" cmd /k "cd frontend && npm run dev"

echo.
echo Both servers are launching in separate windows!
echo - Backend API:  http://127.0.0.1:8000/docs
echo - Frontend App: http://localhost:5173
echo ========================================================
