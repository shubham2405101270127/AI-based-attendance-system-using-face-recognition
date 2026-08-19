@echo off
title AttendAI Launcher
echo.
echo  Starting AttendAI...
echo  Please wait, this takes about 15 seconds...
echo.

cd /d C:\attendance_system
call venv\Scripts\activate

start "" http://127.0.0.1:8000

timeout /t 5 /nobreak >nul

uvicorn main:app --host 0.0.0.0 --port 8000 --reload