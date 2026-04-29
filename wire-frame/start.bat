@echo off
echo Starting WorkMate...
echo.
echo [1/3] Starting LiveKit Server (WebRTC on :7880)...
docker run --rm -d --name workmate-livekit ^
  -p 7880:7880 -p 7881:7881 -p 7882:7882/udp ^
  -e LIVEKIT_KEYS="workmate_key: workmate_secret" ^
  livekit/livekit-server --dev
timeout /t 2 /nobreak > nul

echo [2/3] Starting Backend (FastAPI on :8000)...
start "WorkMate Backend" cmd /c "cd /d %~dp0back-end && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak > nul

echo [3/3] Starting Frontend (Vite on :5173)...
start "WorkMate Frontend" cmd /c "cd /d %~dp0front-end && npm run dev"
timeout /t 3 /nobreak > nul

echo.
echo WorkMate is running!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8000/docs
echo   LiveKit:  ws://localhost:7880
echo.
echo [Stop LiveKit] docker stop workmate-livekit
echo.
pause
