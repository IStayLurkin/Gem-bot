@echo off
chcp 65001
TITLE GemBot System Launcher

echo =====================================================
echo    🚀 STARTING GEMBOT AI SYSTEM
echo =====================================================

:: --- CRITICAL: FORCE TEMP DIRECTORIES TO G: ---
echo [0/5] Setting TEMP/TMP variables to G:\GemBot\temp
mkdir "G:\GemBot\temp" >nul 2>&1
set TEMP=G:\GemBot\temp
set TMP=G:\GemBot\temp
:: ----------------------------------------------


:: 1. Cleanup Ports
echo [1/5] Clearing Ports...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":7860" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
taskkill /FI "WINDOWTITLE eq Stable Diffusion API" /T /F >nul 2>&1

:: --- PATCH: Silence all Python Warnings for Stable Diffusion ---
set PYTHONWARNINGS=ignore
:: -----------------------------------------------------------------

:: 2. Start Stable Diffusion
echo [2/5] Launching Stable Diffusion...
start "Stable Diffusion API" /d "G:\GemBot\stable-diffusion-webui" webui-user.bat
timeout /t 15 /nobreak >nul

:: 3. Start Discord Bot (Backend)
echo [3/5] Waking up Docker Bot...

:: --- NEW PERSISTENT VOLUME LOGIC ---
:: Define the directory on your G: drive for container persistence.
set BOT_DATA_DIR="G:\GemBot\docker-storage\discord-bot-data"
mkdir %BOT_DATA_DIR% >nul 2>&1

:: Stop and remove old container to apply volume changes
docker stop my-discord-bot 2>nul
docker rm my-discord-bot 2>nul

:: Create and run the new container, mounting the G: drive directory to a new /data folder
:: The code stays in /bot; the data goes to /data
docker run -d --restart unless-stopped --name my-discord-bot ^
-v %BOT_DATA_DIR%:/data ^
--add-host=host.docker.internal:host-gateway gembot

:: --- END NEW VOLUME LOGIC ---

:: 4. Start OmniBot Web Server (Frontend)
echo [4/5] Starting OmniBot Web Server...
docker stop omnibot-web 2>nul
docker rm omnibot-web 2>nul
docker run -d --restart unless-stopped --name omnibot-web -p 8080:80 omnibot-v2

echo.
echo [5/5] Opening OmniBot in browser...
start http://localhost:8080
echo.
echo ✅ SYSTEM LIVE! 
echo    - Docker Persistence Forced to: %BOT_DATA_DIR%
echo.
pause