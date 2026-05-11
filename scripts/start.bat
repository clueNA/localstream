@echo off
setlocal

set "PYTHONPATH=%PYTHONPATH%;%cd%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = if ($env:PORT) { $env:PORT } else { '8000' }; " ^
  "$streamlitPort = if ($env:STREAMLIT_PORT) { $env:STREAMLIT_PORT } else { '8501' }; " ^
  "$uvicorn = Start-Process -FilePath python -ArgumentList @('-m','uvicorn','backend.app:app','--host','localhost','--port',$port) -PassThru; " ^
  "$streamlit = Start-Process -FilePath python -ArgumentList @('-m','streamlit','run','backend/admin_app.py','--server.address','localhost','--server.port',$streamlitPort,'--server.headless','true') -PassThru; " ^
  "Wait-Process -Id $uvicorn.Id,$streamlit.Id -Any; " ^
  "Get-Process -Id $uvicorn.Id,$streamlit.Id -ErrorAction SilentlyContinue | Stop-Process -Force"
