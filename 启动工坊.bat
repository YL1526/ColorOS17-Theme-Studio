@echo off
chcp 65001 >nul
title ColorOS 17 主题工坊
cd /d "%~dp0"
setlocal

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not defined PY set "PY=python"

echo.
echo   ColorOS 17 主题工坊 / Theme Studio
echo   Python: %PY%
echo.

"%PY%" server.py %*
if errorlevel 3 exit /b 0
if errorlevel 1 (
  echo.
  echo   [启动失败] 请把上面的错误信息发给助手。
  echo.
  pause
  exit /b 1
)

echo.
echo   服务已停止。
pause
