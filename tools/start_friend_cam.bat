@echo off
title CCTV Friend Camera Streamer
chcp 65001 >nul
cls
echo ======================================================================
echo           🎥 CCTV Friend Camera - ตัวแชร์กล้องผ่าน Tailscale
echo ======================================================================
echo.

:: ตรวจสอบ Python
python --version >nul 2>&1
if errorlevel 1 (
    py -3 --version >nul 2>&1
    if errorlevel 1 (
        echo [X] ไม่พบ Python ในเครื่อง!
        echo กรุณาติดตั้ง Python 3 จาก https://www.python.org/downloads/
        echo **ข้อสำคัญ: ตอนติดตั้งให้ติ๊กถูกที่ 'Add python.exe to PATH' ด้วย**
        echo.
        pause
        exit /b 1
    ) else (
        set PYCMD=py -3
    )
) else (
    set PYCMD=python
)

echo [*] ตรวจสอบและติดตั้งโมดูลที่จำเป็น (Flask, OpenCV)...
%PYCMD% -m pip install --quiet flask opencv-python

echo [*] กำลังเปิดกล้องเว็บแคม...
echo.
%PYCMD% "%~dp0friend_cam.py"

if errorlevel 1 (
    echo.
    echo [X] สตรีมหยุดทำงานด้วยข้อผิดพลาด ตรวจสอบข้อความด้านบน
    pause
)
