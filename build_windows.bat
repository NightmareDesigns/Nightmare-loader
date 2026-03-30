@echo off
:: build_windows.bat
:: Build a standalone Windows .exe for Nightmare Loader using PyInstaller.
::
:: Requirements:
::   - Python 3.9+ on PATH
::   - Run from the repository root
::
:: Output: dist\nightmare-loader.exe

setlocal

echo ============================================================
echo  Nightmare Loader -- Windows Build
echo ============================================================
echo.

:: Step 1 – install build dependencies into the current environment
echo [1/3] Installing package and PyInstaller...
pip install --upgrade pip
pip install -e ".[windows]"
if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
)
echo.

:: Step 2 – run PyInstaller
echo [2/3] Building with PyInstaller...
pyinstaller --clean nightmare-loader.spec
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    exit /b 1
)
echo.

:: Step 3 – report
echo [3/3] Build complete!
echo.
echo   Executable : dist\nightmare-loader.exe
echo.
echo Usage:
echo   dist\nightmare-loader.exe ui              ^(open web UI^)
echo   dist\nightmare-loader.exe --help          ^(CLI help^)
echo   dist\nightmare-loader.exe install-launcher ^(create Start Menu shortcut^)
echo.

endlocal
