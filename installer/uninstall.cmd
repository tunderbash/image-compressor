@echo off
setlocal
title Image Compressor - Uninstall

set "APPNAME=Image Compressor"
set "EXENAME=ImageCompressor.exe"
set "INSTALLDIR=%~dp0"
if "%INSTALLDIR:~-1%"=="\" set "INSTALLDIR=%INSTALLDIR:~0,-1%"

echo ============================================
echo   %APPNAME% - Uninstall
echo ============================================
echo.

echo [1/4] Closing the app if it is running...
taskkill /im %EXENAME% /f >nul 2>&1

echo [2/4] Removing shortcuts...
set "STARTLNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Image Compressor.lnk"
if exist "%STARTLNK%" del /f /q "%STARTLNK%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$p = Join-Path $desktop 'Image Compressor.lnk';" ^
  "if (Test-Path $p) { Remove-Item $p -Force }"

echo [3/4] Removing the Apps ^& Features entry...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ImageCompressor' -Recurse -Force -ErrorAction SilentlyContinue"

echo [4/4] Removing installed files...
rem The uninstaller lives inside the install folder, so delete the folder
rem after this script exits: spawn a detached helper that waits, then deletes.
set "HELPER=%TEMP%\ic_cleanup_%RANDOM%.bat"
> "%HELPER%" echo @echo off
>>"%HELPER%" echo cd /d "%%TEMP%%"
>>"%HELPER%" echo timeout /t 2 /nobreak ^>nul
>>"%HELPER%" echo rmdir /s /q "%INSTALLDIR%"
>>"%HELPER%" echo del /f /q "%%~f0"
start "" /b "%HELPER%"

echo.
echo %APPNAME% has been removed.
echo.
endlocal
exit /b 0
