@echo off
set ENV_NAME=trae-env
set PYTHON_VERSION=3.11

:: Detect OS
ver | findstr /i "Windows" > nul
if %errorlevel%==0 (
    echo Detected OS: Windows
    goto setup_windows
) else (
    echo Detected OS: Unix-like (macOS/Linux)
    goto setup_mac
)

:setup_windows
echo.
echo === Creating conda environment "%ENV_NAME%" with Python %PYTHON_VERSION% ===
conda create -n %ENV_NAME% python=%PYTHON_VERSION% -y
call conda activate %ENV_NAME%

echo.
echo === Installing dependencies from requirements.txt ===
pip install -r requirements.txt

echo.
echo === Installing FFmpeg via Chocolatey (if available) ===
where choco > nul
if %errorlevel%==0 (
    choco install ffmpeg -y
) else (
    echo ⚠ Chocolatey not found. Please install FFmpeg manually or install Chocolatey from https://chocolatey.org/install
)

echo.
echo ✅ Environment setup complete!
echo 💡 To start the tool:
echo     conda activate %ENV_NAME%
echo     python gradio_ui.py
goto end

:setup_mac
echo.
echo === Creating conda environment "%ENV_NAME%" with Python %PYTHON_VERSION% ===
conda create -n %ENV_NAME% python=%PYTHON_VERSION% -y
conda activate %ENV_NAME%

echo.
echo === Installing dependencies from requirements.txt ===
pip install -r requirements.txt

echo.
echo === Installing FFmpeg using Homebrew ===
which brew > /dev/null
if %errorlevel%==0 (
    brew install ffmpeg
) else (
    echo ⚠ Homebrew not found. Please install FFmpeg manually or install Homebrew from https://brew.sh
)

echo.
echo ✅ Environment setup complete!
echo 💡 To start the tool:
echo     conda activate %ENV_NAME%
echo     python3 gradio_ui.py
goto end

:end
pause