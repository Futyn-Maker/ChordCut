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

REM Check Python
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.13+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    if !INTERACTIVE!==1 pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Found Python %PYVER%
echo.

REM Check/install dependencies
echo Installing/updating dependencies...
pip install --upgrade pip >nul 2>&1
pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies from requirements.txt
    if !INTERACTIVE!==1 pause
    exit /b 1
)
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install pyinstaller
    if !INTERACTIVE!==1 pause
    exit /b 1
)
echo Dependencies installed successfully.
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
        echo The build will continue, but the app won't work without libmpv!
        echo.
        pause
    )
)
echo.

REM Compile translations (.po to .mo)
echo Compiling translations...
if exist "locale" (
    for /d %%l in (locale\*) do (
        if exist "%%l\LC_MESSAGES\chordcut.po" (
            echo   Compiling %%~nl translation...
            msgfmt -o "%%l\LC_MESSAGES\chordcut.mo" "%%l\LC_MESSAGES\chordcut.po" 2>nul
            if errorlevel 1 (
                echo   WARNING: Failed to compile %%~nl translation - msgfmt not found or error
            )
        )
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
        echo   Converting %%f to readme_!DOCLANG!.html...
        pandoc --standalone --embed-resources --css=build/docs.css --metadata title="ChordCut" --metadata lang=!DOCLANG! -o "dist\ChordCut\readme_!DOCLANG!.html" "%%f"
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
echo    Build Complete!
echo ============================================
echo.
echo Output folder: dist\ChordCut\
echo Executable:    dist\ChordCut\ChordCut.exe
echo.
echo To run: double-click dist\ChordCut\ChordCut.exe
echo.

if !INTERACTIVE!==1 pause
