@echo off
cd /d "%~dp0"
title Ajan Hali - Endustriyel Desinator CAD/CAM Studyosu
color 0B
echo ================================================================
echo   AJAN HALI - CAD/CAM & IPLIK RECEPTESI OPTIMIZASYON STUDYOSU
echo   Telif Hakki (c) 2026 Seydi Eryilmaz (@seydivakkas)
echo ================================================================
echo.
echo Sunucu baslatiliyor (http://127.0.0.1:8001)...
echo Tarayiciniz otomatik olarak acilacaktir.
echo.
start "" http://127.0.0.1:8001/
python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
pause
