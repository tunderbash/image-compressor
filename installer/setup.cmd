@echo off
setlocal enabledelayedexpansion
title Image Compressor - Setup

set "APPNAME=Image Compressor"
set "EXENAME=ImageCompressor.exe"
set "DEFAULTDIR=%LOCALAPPDATA%\Programs\ImageCompressor"
set "SRC=%~dp0"

echo ============================================
echo   %APPNAME% Setup
echo ============================================
echo.

rem --- Ask the user where to install (graphical folder picker) ---
rem If INSTALLDIR was already provided (e.g. a silent/scripted install),
rem keep it and skip the dialog.
if not defined INSTALLDIR (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Add-Type -AssemblyName System.Windows.Forms | Out-Null;" ^
      "$d = New-Object System.Windows.Forms.FolderBrowserDialog;" ^
      "$d.Description = 'Choose a folder to install Image Compressor';" ^
      "$d.SelectedPath = '%DEFAULTDIR%';" ^
      "$d.ShowNewFolderButton = $true;" ^
      "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }"`) do set "INSTALLDIR=%%I"
)

rem Fall back to the default if the user just closed the dialog.
if not defined INSTALLDIR set "INSTALLDIR=%DEFAULTDIR%"

echo Installing to: "%INSTALLDIR%"
echo.

if not exist "%SRC%%EXENAME%" (
    echo [ERROR] "%EXENAME%" was not found next to the setup.
    pause
    exit /b 1
)

echo [1/4] Copying files...
if not exist "%INSTALLDIR%" mkdir "%INSTALLDIR%" 2>nul
copy /y "%SRC%%EXENAME%" "%INSTALLDIR%\%EXENAME%" >nul
if errorlevel 1 ( echo [ERROR] Could not copy the application. & pause & exit /b 1 )

rem Ship a per-install uninstaller (paths are resolved at run time).
if exist "%SRC%uninstall.cmd" copy /y "%SRC%uninstall.cmd" "%INSTALLDIR%\uninstall.cmd" >nul

echo [2/4] Creating shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$target = Join-Path '%INSTALLDIR%' '%EXENAME%';" ^
  "$wd = '%INSTALLDIR%';" ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$start = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Image Compressor.lnk';" ^
  "$s = $ws.CreateShortcut($start); $s.TargetPath = $target; $s.WorkingDirectory = $wd; $s.IconLocation = $target; $s.Description = 'Image Compressor'; $s.Save();" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$d = $ws.CreateShortcut((Join-Path $desktop 'Image Compressor.lnk')); $d.TargetPath = $target; $d.WorkingDirectory = $wd; $d.IconLocation = $target; $d.Save();"

echo [3/4] Registering in Apps ^& Features...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ImageCompressor';" ^
  "New-Item -Path $key -Force | Out-Null;" ^
  "$target = Join-Path '%INSTALLDIR%' '%EXENAME%';" ^
  "Set-ItemProperty -Path $key -Name DisplayName -Value 'Image Compressor';" ^
  "Set-ItemProperty -Path $key -Name DisplayVersion -Value '1.0.0';" ^
  "Set-ItemProperty -Path $key -Name Publisher -Value 'tunderbash';" ^
  "Set-ItemProperty -Path $key -Name DisplayIcon -Value $target;" ^
  "Set-ItemProperty -Path $key -Name InstallLocation -Value '%INSTALLDIR%';" ^
  "Set-ItemProperty -Path $key -Name UninstallString -Value ('\"' + (Join-Path '%INSTALLDIR%' 'uninstall.cmd') + '\"');" ^
  "Set-ItemProperty -Path $key -Name NoModify -Value 1 -Type DWord;" ^
  "Set-ItemProperty -Path $key -Name NoRepair -Value 1 -Type DWord;"

echo [4/4] Done.
echo.
echo ============================================
echo   %APPNAME% is installed.
echo   Uninstall from "Apps ^& Features" or run
echo   "%INSTALLDIR%\uninstall.cmd".
echo ============================================
echo.

choice /m "Launch %APPNAME% now" /c YN /n
if errorlevel 2 goto end
start "" "%INSTALLDIR%\%EXENAME%"

:end
endlocal
