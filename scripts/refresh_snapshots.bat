@echo off
REM 폴백 스냅샷 주간 자동 갱신 (국내 IP에서 실행되어야 함)
REM Windows 작업 스케줄러에 등록해 주 1회 자동 실행한다. 로그는 %TEMP%에 남는다.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\정용희\Desktop\이항모형"
echo ===== %DATE% %TIME% ===== >> "%TEMP%\refresh_snapshots.log"
python scripts\refresh_snapshots.py --push >> "%TEMP%\refresh_snapshots.log" 2>&1
