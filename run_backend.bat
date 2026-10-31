@echo off
cd backend
echo Starting Backend API at http://127.0.0.1:8000 ...
.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
