@echo off
setlocal

echo ============================================
echo  AI QA Agent - Local Web UI
echo ============================================

if not exist venv (
    echo Membuat virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Gagal membuat virtual environment. Pastikan Python 3.10+ terinstal.
        pause
        exit /b 1
    )
)

echo Menginstall dependency...
venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo Gagal menginstall dependency.
    pause
    exit /b 1
)

echo.
echo Menjalankan aplikasi di http://127.0.0.1:8001
echo Tekan Ctrl+C untuk berhenti.
echo.

venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

pause
