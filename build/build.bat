@echo off
setlocal enabledelayedexpansion

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
    pause
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
    pause
    exit /b 1
)
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install pyinstaller
    pause
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
    echo WARNING: libmpv DLL not found in resources\libmpv\
    echo.
    echo Please download libmpv from:
    echo   https://sourceforge.net/projects/mpv-player-windows/files/libmpv/
    echo.
    echo Extract mpv-2.dll ^(or libmpv-2.dll^) to the resources\libmpv\ folder
    echo.
    echo The build will continue, but the app won't work without libmpv!
    echo.
    pause
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
    pause
    exit /b 1
)

REM Create data folder
echo.
echo Creating data folder...
if not exist "dist\ChordCut\data" mkdir "dist\ChordCut\data"

REM Copy locale folder (translations - only .mo files)
echo Copying translations...
if exist "locale" (
    for /d %%l in (locale\*) do (
        if exist "%%l\LC_MESSAGES\chordcut.mo" (
            if not exist "dist\ChordCut\locale\%%~nxl\LC_MESSAGES" mkdir "dist\ChordCut\locale\%%~nxl\LC_MESSAGES"
            copy /Y "%%l\LC_MESSAGES\chordcut.mo" "dist\ChordCut\locale\%%~nxl\LC_MESSAGES\" >nul
            echo   Copied %%~nxl translation
        )
    )
) else (
    echo   No locale folder found, skipping.
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

pause
