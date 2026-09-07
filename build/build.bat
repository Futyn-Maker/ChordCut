@echo off
setlocal enabledelayedexpansion

REM Detect CI environment (GitHub Actions sets CI=true automatically)
if defined CI (set "INTERACTIVE=0") else (set "INTERACTIVE=1")

echo ============================================
echo    ChordCut Build Script
echo ============================================
echo.

REM Change to project root directory
cd /d "%~dp0.."

REM Let Windows PowerShell rebuild its default module path. When this script is
REM launched from PowerShell 7 the inherited path lists PowerShell 7's modules
REM first, and the powershell.exe calls below (uv installer, libmpv download)
REM fail to load their own Security module.
set "PSModulePath="

REM ---------------------------------------------------------------------------
REM Project environment
REM
REM Everything runs inside the project's virtual environment (.venv). The
REM dependencies are declared in pyproject.toml only: the app's own under
REM [project], and the build tools (PyInstaller, Babel) in the "dev" group.
REM
REM   1. An existing .venv is reused and brought up to date.
REM   2. Otherwise it is created with uv when available, else with the venv
REM      module of a Python 3.12+ found on PATH.
REM   3. With neither, uv is installed; it fetches a suitable Python itself
REM      (the version pinned in .python-version).
REM ---------------------------------------------------------------------------
echo Preparing the project environment...
call :find_uv

if exist ".venv\Scripts\python.exe" (
    echo Using the existing virtual environment in .venv
) else if defined UV (
    echo Creating the virtual environment with uv...
) else (
    call :find_python
    if defined PYTHON (
        echo Creating the virtual environment with "!PYTHON! -m venv"...
        call !PYTHON! -m venv .venv
        if errorlevel 1 (
            echo ERROR: Failed to create the virtual environment.
            if !INTERACTIVE!==1 pause
            exit /b 1
        )
    ) else (
        call :install_uv
        if not defined UV (
            if !INTERACTIVE!==1 pause
            exit /b 1
        )
    )
)

if defined UV (
    echo Syncing dependencies with uv...
    "!UV!" sync
    if errorlevel 1 (
        echo ERROR: uv could not set up the environment. Fix the error above,
        echo or delete the .venv folder and run this script again.
        if !INTERACTIVE!==1 pause
        exit /b 1
    )
) else (
    echo Installing dependencies with pip...
    REM A uv-created environment ships without pip; ensurepip adds it. Dependency
    REM groups need pip 25.1 or newer, hence the upgrade.
    ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
    if errorlevel 1 echo   WARNING: Could not upgrade pip; version 25.1+ is needed for dependency groups.
    ".venv\Scripts\python.exe" -m pip install -e . --group dev
    if errorlevel 1 (
        echo ERROR: Failed to install the dependencies from pyproject.toml. Fix the
        echo error above, or delete the .venv folder and run this script again.
        if !INTERACTIVE!==1 pause
        exit /b 1
    )
)

REM From here on python, pyinstaller and pybabel are the environment's own.
call ".venv\Scripts\activate.bat"
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Environment ready: Python %PYVER% in .venv
echo.

REM Check for libmpv
echo Checking for libmpv...
set LIBMPV_FOUND=0
if exist "resources\libmpv\mpv-2.dll" set LIBMPV_FOUND=1
if exist "resources\libmpv\libmpv-2.dll" set LIBMPV_FOUND=1
if exist "resources\libmpv\mpv-1.dll" set LIBMPV_FOUND=1

if %LIBMPV_FOUND%==0 (
    echo.
    if !INTERACTIVE!==0 (
        echo ERROR: libmpv DLL not found in resources\libmpv\
        echo Run build\download_libmpv.ps1 before calling this script.
        exit /b 1
    )
    echo libmpv DLL not found in resources\libmpv\
    echo.
    set /p DOWNLOAD_MPV="Would you like to download it automatically? (Y/N): "
    if /i "!DOWNLOAD_MPV!"=="Y" (
        powershell -ExecutionPolicy Bypass -File "build\download_libmpv.ps1" -OutputDir "resources\libmpv"
        if errorlevel 1 (
            echo.
            echo Automatic download failed. Please download libmpv manually from:
            echo   https://sourceforge.net/projects/mpv-player-windows/files/libmpv/
            echo Extract libmpv-2.dll to the resources\libmpv\ folder.
            echo.
            pause
            exit /b 1
        )
        echo.
    ) else (
        echo.
        echo Skipping libmpv download.
        echo The build will continue, but the app won't work without libmpv^^!
        echo.
        pause
    )
)
echo.

REM Compile translations (.po to .mo)
echo Compiling translations...
if exist "locale" (
    pybabel compile -d locale -D chordcut 2>nul
    if errorlevel 1 (
        echo   WARNING: Failed to compile translations.
    )
) else (
    echo   No locale folder found, skipping translations.
)
echo.

REM Clean previous build
echo Cleaning previous build...
if exist "dist\ChordCut" rmdir /s /q "dist\ChordCut"
if exist "build\ChordCut" rmdir /s /q "build\ChordCut"
echo.

REM Build
echo Building ChordCut...
echo.
pyinstaller --clean --noconfirm build/chordcut.spec
if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    if !INTERACTIVE!==1 pause
    exit /b 1
)

REM Create data folder
echo.
echo Creating data folder...
if not exist "dist\ChordCut\data" mkdir "dist\ChordCut\data"

REM Copy wxWidgets built-in translations (wxstd.mo) for standard button labels
REM (app translations are bundled by PyInstaller via the spec's datas)
echo Copying wx translations...
for /f "delims=" %%W in ('python -c "import wx, os; print(os.path.join(os.path.dirname(wx.__file__), 'locale'))"') do set WX_LOCALE=%%W
if exist "%WX_LOCALE%" (
    for /d %%l in (locale\*) do (
        set LANG_CODE=%%~nxl
        if exist "%WX_LOCALE%\!LANG_CODE!\LC_MESSAGES\wxstd.mo" (
            if not exist "dist\ChordCut\_internal\locale\!LANG_CODE!\LC_MESSAGES" mkdir "dist\ChordCut\_internal\locale\!LANG_CODE!\LC_MESSAGES"
            copy /Y "%WX_LOCALE%\!LANG_CODE!\LC_MESSAGES\wxstd.mo" "dist\ChordCut\_internal\locale\!LANG_CODE!\LC_MESSAGES\" >nul
            echo   Copied wx translation for !LANG_CODE!
        )
    )
) else (
    echo   WARNING: wx locale directory not found, standard buttons may not be translated.
)

REM Generate documentation
echo.
echo Generating documentation...

REM Copy any existing HTML docs as a baseline (may be overwritten by pandoc below)
set DOCS_AVAILABLE=0
for %%f in (readme*.html) do (
    echo   Copying existing %%f...
    copy /Y "%%f" "dist\ChordCut\" >nul
    set DOCS_AVAILABLE=1
)

REM Try to build fresh docs with pandoc (overwrites any copied files if successful)
pandoc --version >nul 2>&1
if not errorlevel 1 (
    for %%f in (README*.md) do (
        set "BASE=%%~nf"
        set "DOCLANG=!BASE:README=!"
        if "!DOCLANG!"=="" set "DOCLANG=en"
        if "!DOCLANG:~0,1!"=="_" set "DOCLANG=!DOCLANG:~1!"
        echo   Converting %%f to readme_!DOCLANG!.html...
        REM Template, stylesheet and filter live in build\ (docs.html, docs.css, docs.lua).
        REM The filter takes the title and download link from the README itself.
        pandoc --standalone --embed-resources --template=build/docs.html --css=build/docs.css --lua-filter=build/docs.lua --toc --toc-depth=3 --metadata lang=!DOCLANG! -o "dist\ChordCut\readme_!DOCLANG!.html" "%%f"
        if not errorlevel 1 set DOCS_AVAILABLE=1
    )
) else (
    echo   WARNING: Pandoc not found - documentation will not be rebuilt.
    echo   Install from https://pandoc.org/installing.html to generate docs.
)

if !DOCS_AVAILABLE!==0 (
    echo   WARNING: No HTML documentation available in output.
)

echo.
echo ============================================
echo    Build Complete^^!
echo ============================================
echo.
echo Output folder: dist\ChordCut\
echo Executable:    dist\ChordCut\ChordCut.exe
echo.
echo To run: double-click dist\ChordCut\ChordCut.exe
echo.

if !INTERACTIVE!==1 pause

exit /b 0

REM ---------------------------------------------------------------------------
REM Subroutines
REM ---------------------------------------------------------------------------

:find_uv
REM Sets UV to the uv executable: from PATH, or from the installer's target
REM directory (UV_UNMANAGED_INSTALL or UV_INSTALL_DIR when set, otherwise
REM %USERPROFILE%\.local\bin), where a freshly installed uv sits before PATH
REM is refreshed.
set "UV="
for /f "delims=" %%p in ('where uv 2^>nul') do if not defined UV set "UV=%%p"
if not defined UV if defined UV_UNMANAGED_INSTALL if exist "%UV_UNMANAGED_INSTALL%\uv.exe" set "UV=%UV_UNMANAGED_INSTALL%\uv.exe"
if not defined UV if defined UV_INSTALL_DIR if exist "%UV_INSTALL_DIR%\uv.exe" set "UV=%UV_INSTALL_DIR%\uv.exe"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
exit /b 0

:find_python
REM Sets PYTHON to a Python 3.12+ command (the floor is requires-python in
REM pyproject.toml): "python" from PATH, else the py launcher's newest 3.x.
REM "call" keeps control here even when python is a .bat shim (pyenv-win).
set "PYTHON="
call python -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON (
    call py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1 && set "PYTHON=py -3"
)
exit /b 0

:install_uv
echo Neither uv nor Python 3.12+ was found.
if !INTERACTIVE!==1 (
    set /p INSTALL_UV="Install uv now? It also downloads the Python this project needs. (Y/N): "
    if /i not "!INSTALL_UV!"=="Y" (
        echo.
        echo Install uv from https://docs.astral.sh/uv/ or Python 3.12+ from https://python.org
        echo and run this script again.
        exit /b 1
    )
)
echo Installing uv...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 (
    echo ERROR: The uv installer failed. Install uv from https://docs.astral.sh/uv/
    echo or Python 3.12+ from https://python.org and run this script again.
    exit /b 1
)
call :find_uv
if not defined UV (
    echo ERROR: uv was installed but could not be located. Open a new terminal
    echo and run this script again.
    exit /b 1
)
exit /b 0
