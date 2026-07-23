@echo off
cd /d "C:\Users\radim\AI_Engineer\ai-news-agent"

echo ============================== >> scheduler.log
echo START %date% %time% >> scheduler.log

"C:\Users\radim\AI_Engineer\ai-news-agent\venv\Scripts\python.exe" ai-news-agent.py >> scheduler.log 2>&1

set EXITCODE=%ERRORLEVEL%

echo END %date% %time% >> scheduler.log
echo ExitCode=%EXITCODE% >> scheduler.log
echo. >> scheduler.log

exit /b %EXITCODE%