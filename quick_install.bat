@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: AstrBot Desktop Assistant - Windows Quick Install Script
:: ============================================================================
:: Features:
::   1. Simple network environment selection (Direct/Proxy)
::   2. Auto-detect and select fastest proxy
::   3. Fully automated installation
::   4. Auto-create desktop shortcut and autostart
:: ============================================================================

title AstrBot Desktop Assistant Quick Install

:: GitHub repository URL
set "GITHUB_REPO=https://github.com/muyouzhi6/Astrbot-desktop-assistant.git"

:: Proxy list for China users
set "PROXY_HOSTS=gh.llkk.cc gh-proxy.com mirror.ghproxy.com ghproxy.net"

echo.
echo ======================================================================
echo         AstrBot Desktop Assistant Quick Install Script
echo ======================================================================
echo.
echo         + One-click installation, just one choice!
echo.

:: ============================================================================
:: Network environment selection
:: ============================================================================
echo Select your network environment:
echo.
echo   1 - Direct access to GitHub - overseas network
echo   2 - Use proxy - recommended for China users
echo.
set /p "NETWORK_CHOICE=Select 1 or 2: "

if "!NETWORK_CHOICE!"=="1" (
    set "USE_PROXY=0"
    echo.
    echo + Using direct GitHub connection
) else (
    set "USE_PROXY=1"
    echo.
    echo Testing proxy servers, please wait...
)

set "CLONE_URL=%GITHUB_REPO%"
set "BEST_PROXY="

:: ============================================================================
:: Auto-test proxy availability using the real Git smart-HTTP endpoint
:: ============================================================================
if "!USE_PROXY!"=="1" (
    echo.
    set "CLONE_URLS="

    for %%H in (%PROXY_HOSTS%) do (
        echo   Testing %%H ...

        set "PROXY_CLONE_URL=https://%%H/!GITHUB_REPO!"
        set "PROXY_PROBE_URL=https://%%H/!GITHUB_REPO!/info/refs?service=git-upload-pack"
        powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $ProgressPreference = 'SilentlyContinue'; $response = Invoke-WebRequest -UseBasicParsing -Uri $env:PROXY_PROBE_URL -Method Get -TimeoutSec 8; if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            if not defined BEST_PROXY (
                set "BEST_PROXY=%%H"
                set "CLONE_URL=!PROXY_CLONE_URL!"
            )
            set "CLONE_URLS=!CLONE_URLS! !PROXY_CLONE_URL!"
            echo     + Available
        ) else (
            echo     X Unavailable
        )
    )

    if defined BEST_PROXY (
        echo.
        echo + Selected proxy: !BEST_PROXY!
    ) else (
        echo.
        echo X All proxies unavailable.
        echo   You selected proxy mode, so direct GitHub will not be used automatically.
        echo   Please choose option 1 if your network can access GitHub directly.
    )
)

:: ============================================================================
:: Check Git
:: ============================================================================
echo.
echo Step 1 of 6 - Checking Git environment...

git --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ======================================================================
    echo   X Git not detected. Please install Git first.
    echo ======================================================================
    echo.
    echo   Download: https://git-scm.com/downloads
    echo.
    echo   Keep default options during installation.
    echo.
    pause
    exit /b 1
)
echo + Git is installed

:: ============================================================================
:: Check Python
:: ============================================================================
echo.
echo Step 2 of 6 - Checking Python environment...

set "PYTHON_CMD="

:: Try multiple ways to find Python
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

python3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)

py --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=py"
    goto :python_found
)

:: Check common installation paths
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%PROGRAMFILES%\Python312\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "%PROGRAMFILES%\Python310\python.exe"
) do (
    if exist %%P (
        set "PYTHON_CMD=%%~P"
        goto :python_found
    )
)

:: Python not found
echo.
echo ======================================================================
echo   X Python 3.10+ not detected. Please install Python first.
echo ======================================================================
echo.
echo   Download: https://www.python.org/downloads/
echo.
echo   ! Make sure to check "Add Python to PATH" during installation
echo.
pause
exit /b 1

:python_found
:: Get Python version
for /f "tokens=2" %%V in ('!PYTHON_CMD! --version 2^>^&1') do set "PYTHON_VERSION=%%V"
echo + Python %PYTHON_VERSION% is installed

:: Check version meets requirements (>= 3.10)
for /f "tokens=1,2 delims=." %%A in ("%PYTHON_VERSION%") do (
    set "PY_MAJOR=%%A"
    set "PY_MINOR=%%B"
)
if %PY_MAJOR% LSS 3 (
    echo X Python version too low, requires 3.10 or higher
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 10 (
    echo X Python version too low, requires 3.10 or higher
    pause
    exit /b 1
)

:: ============================================================================
:: Clone project
:: ============================================================================
echo.
echo Step 3 of 6 - Downloading project...

set "PROJECT_DIR=%CD%\Astrbot-desktop-assistant"

if exist "!PROJECT_DIR!\.git" (
    echo Existing project detected, updating...
    cd /d "!PROJECT_DIR!"
    git pull
    if !ERRORLEVEL! NEQ 0 (
        echo ! Update failed, trying to re-clone...
        cd /d "%CD%"
        rmdir /s /q "!PROJECT_DIR!" 2>nul
        goto :clone_project
    )
    echo + Project updated
    goto :after_clone
)

:clone_project
if exist "!PROJECT_DIR!" (
    rmdir /s /q "!PROJECT_DIR!" 2>nul
)

echo Downloading project using shallow clone...
echo.

set "CLONE_OK=0"

if "!USE_PROXY!"=="1" (
    if not defined CLONE_URLS (
        echo X No verified proxy is available. Download aborted.
        pause
        exit /b 1
    )

    for %%U in (!CLONE_URLS!) do (
        if "!CLONE_OK!"=="0" (
            if exist "!PROJECT_DIR!" (
                rmdir /s /q "!PROJECT_DIR!" 2>nul
            )
            echo Download URL: %%U
            git clone --depth 1 "%%U" "!PROJECT_DIR!"
            if !ERRORLEVEL! EQU 0 (
                set "CLONE_OK=1"
            ) else (
                echo ! Download failed with this proxy, trying next verified proxy...
            )
        )
    )

    if "!CLONE_OK!"=="0" (
        echo X Download failed through all verified proxies.
        echo   Direct GitHub fallback is skipped because proxy mode was selected.
        pause
        exit /b 1
    )
) else (
    echo Download URL: !CLONE_URL!
    git clone --depth 1 "!CLONE_URL!" "!PROJECT_DIR!"
    if !ERRORLEVEL! NEQ 0 (
        echo X Download failed. Please check network connection.
        pause
        exit /b 1
    ) else (
        set "CLONE_OK=1"
    )
)

echo + Project downloaded

:after_clone
cd /d "!PROJECT_DIR!"

:: Display version info
echo.
echo Version Info:
for /f "usebackq tokens=*" %%i in (`git log -1 --format^="%%h %%ci %%s"`) do (
    echo   Latest commit: %%i
)

:: ============================================================================
:: Create virtual environment and install dependencies
:: ============================================================================
echo.
echo Step 4 of 6 - Configuring Python environment...

set "VENV_DIR=!PROJECT_DIR!\venv"

if exist "!VENV_DIR!\Scripts\python.exe" (
    echo + Virtual environment already exists
) else (
    echo Creating virtual environment...
    "!PYTHON_CMD!" -m venv "!VENV_DIR!"
    if !ERRORLEVEL! NEQ 0 (
        echo ! Failed to create virtual environment, using system Python
    ) else (
        echo + Virtual environment created
    )
)

:: Set Python path
if exist "!VENV_DIR!\Scripts\python.exe" (
    set "PYTHON_CMD=!VENV_DIR!\Scripts\python.exe"
)

echo.
echo Step 5 of 6 - Installing dependencies - this may take a few minutes...

:: Upgrade pip
"!PYTHON_CMD!" -m pip install --upgrade pip -q 2>nul

:: Install dependencies
"!PYTHON_CMD!" -m pip install -r "!PROJECT_DIR!\requirements.txt" -q
if !ERRORLEVEL! NEQ 0 (
    echo ! Some dependencies failed, trying to install core dependencies individually...
    
    for %%D in (
        "PySide6>=6.5.0"
        "qasync>=0.27.1"
        "httpx[http2]>=0.24.0"
        "websockets>=11.0.0"
        "Pillow>=9.0.0"
        "mss>=9.0.0"
        "pynput>=1.7.0"
    ) do (
        echo   Installing %%~D...
        "!PYTHON_CMD!" -m pip install %%~D -q 2>nul
    )
)

echo + Dependencies installed

:: ============================================================================
:: Auto configuration (desktop shortcut + autostart)
:: ============================================================================
echo.
echo Step 6 of 6 - Auto configuration...

:: Create desktop shortcut
set "SHORTCUT_VBS=%TEMP%\create_shortcut.vbs"
set "DESKTOP=%USERPROFILE%\Desktop"

:: Use virtual environment pythonw.exe
if exist "!VENV_DIR!\Scripts\pythonw.exe" (
    set "TARGET_SCRIPT=!VENV_DIR!\Scripts\pythonw.exe"
    set "ARGUMENTS=-m desktop_client"
) else (
    set "TARGET_SCRIPT=!PROJECT_DIR!\start.bat"
    set "ARGUMENTS="
)

echo Set oWS = WScript.CreateObject^("WScript.Shell"^) > "!SHORTCUT_VBS!"
echo sLinkFile = "!DESKTOP!\AstrBot Desktop Assistant.lnk" >> "!SHORTCUT_VBS!"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^) >> "!SHORTCUT_VBS!"
echo oLink.TargetPath = "!TARGET_SCRIPT!" >> "!SHORTCUT_VBS!"
if not "!ARGUMENTS!"=="" (
    echo oLink.Arguments = "!ARGUMENTS!" >> "!SHORTCUT_VBS!"
)
echo oLink.WorkingDirectory = "!PROJECT_DIR!" >> "!SHORTCUT_VBS!"
echo oLink.Description = "AstrBot Desktop Assistant" >> "!SHORTCUT_VBS!"
echo oLink.Save >> "!SHORTCUT_VBS!"

cscript //nologo "!SHORTCUT_VBS!" 2>nul
del "!SHORTCUT_VBS!" 2>nul

if exist "!DESKTOP!\AstrBot Desktop Assistant.lnk" (
    echo + Desktop shortcut created
) else (
    echo ! Failed to create desktop shortcut
)

:: Configure autostart
echo Configuring autostart...
"!PYTHON_CMD!" -c "from desktop_client.platforms import get_platform_adapter; adapter = get_platform_adapter(); result = adapter.enable_autostart(); print(result.message if result else '')" 2>nul

if !ERRORLEVEL! EQU 0 (
    echo + Autostart configured
) else (
    echo ! Autostart configuration failed, can be enabled later in settings
)

:: ============================================================================
:: Installation complete
:: ============================================================================
echo.
echo ======================================================================
echo                     + Installation Successful!
echo ======================================================================
echo.
echo   Project directory: !PROJECT_DIR!
echo.
echo   How to start:
echo     - Double-click desktop shortcut "AstrBot Desktop Assistant"
echo     - Or run start.bat
echo.

:: Ask whether to start immediately
echo Start AstrBot Desktop Assistant now?
echo   1 - Yes
echo   2 - No
echo.
set /p "START_CHOICE=Select 1 or 2: "

if "!START_CHOICE!"=="1" (
    echo.
    echo Starting...
    start "" "!PYTHON_CMD!" -m desktop_client
    echo + Application started
)

echo.
echo Thank you for using AstrBot Desktop Assistant!
echo.
pause
