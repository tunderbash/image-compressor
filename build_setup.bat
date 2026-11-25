@echo off
setlocal enabledelayedexpansion
title Image Compressor - Build Setup

set "ROOT=%~dp0"
set "EXENAME=ImageCompressor.exe"
set "STAGE=%ROOT%installer\stage"

echo ============================================
echo   Build Image Compressor setup (.exe)
echo ============================================
echo.

rem --- Locate Python ---
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY ( echo [ERROR] Python not found. Install Python 3.10+. & pause & exit /b 1 )

echo [1/3] Installing dependencies...
"%PY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%PY%" -m pip install --disable-pip-version-check -q -r "%ROOT%requirements.txt"
"%PY%" -m pip install --disable-pip-version-check -q pyinstaller
if errorlevel 1 ( echo [ERROR] Dependency install failed. & pause & exit /b 1 )

echo [2/3] Building a single-file executable...
pushd "%ROOT%"
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ImageCompressor --icon icon.ico ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtWebEngineQuick --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQuick3D ^
  --exclude-module PySide6.QtQuickWidgets --exclude-module PySide6.QtQuickControls2 ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DRender ^
  --exclude-module PySide6.Qt3DExtras --exclude-module PySide6.Qt3DAnimation ^
  --exclude-module PySide6.Qt3DInput --exclude-module PySide6.Qt3DLogic ^
  --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtMultimediaWidgets ^
  --exclude-module PySide6.QtCharts --exclude-module PySide6.QtDataVisualization ^
  --exclude-module PySide6.QtGraphs --exclude-module PySide6.QtGraphsWidgets ^
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtPdfWidgets ^
  --exclude-module PySide6.QtSql --exclude-module PySide6.QtTest ^
  --exclude-module PySide6.QtBluetooth --exclude-module PySide6.QtDesigner ^
  --exclude-module PySide6.QtHelp --exclude-module PySide6.QtLocation ^
  --exclude-module PySide6.QtNetworkAuth --exclude-module PySide6.QtNfc ^
  --exclude-module PySide6.QtPositioning --exclude-module PySide6.QtRemoteObjects ^
  --exclude-module PySide6.QtScxml --exclude-module PySide6.QtSensors ^
  --exclude-module PySide6.QtSerialBus --exclude-module PySide6.QtSerialPort ^
  --exclude-module PySide6.QtSpatialAudio --exclude-module PySide6.QtStateMachine ^
  --exclude-module PySide6.QtSvg --exclude-module PySide6.QtSvgWidgets ^
  --exclude-module PySide6.QtTextToSpeech --exclude-module PySide6.QtWebChannel ^
  --exclude-module PySide6.QtWebSockets --exclude-module PySide6.QtWebView ^
  --exclude-module PySide6.QtXml --exclude-module PySide6.QtUiTools ^
  --exclude-module PySide6.QtOpenGL --exclude-module PySide6.QtOpenGLWidgets ^
  --exclude-module PySide6.QtPrintSupport --exclude-module PySide6.QtHttpServer ^
  --exclude-module PySide6.QtDBus --exclude-module PySide6.QtConcurrent ^
  --exclude-module PySide6.QtCanvasPainter --exclude-module PySide6.QtLabsStyleKit ^
  --exclude-module PySide6.QtAxContainer main.py
set "BUILDERR=%errorlevel%"
popd
if not "%BUILDERR%"=="0" ( echo [ERROR] PyInstaller build failed. & pause & exit /b 1 )
if not exist "%ROOT%dist\%EXENAME%" ( echo [ERROR] dist\%EXENAME% not found. & pause & exit /b 1 )

echo [3/3] Packaging the setup executable...
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"
copy /y "%ROOT%dist\%EXENAME%" "%STAGE%\" >nul
copy /y "%ROOT%installer\setup.cmd" "%STAGE%\" >nul
copy /y "%ROOT%installer\uninstall.cmd" "%STAGE%\" >nul

set "SED=%ROOT%installer\setup.sed"
> "%SED%" echo [Version]
>>"%SED%" echo Class=IEXPRESS
>>"%SED%" echo SEDVersion=3
>>"%SED%" echo [Options]
>>"%SED%" echo PackagePurpose=InstallApp
>>"%SED%" echo ShowInstallProgramWindow=0
>>"%SED%" echo HideExtractAnimation=1
>>"%SED%" echo UseLongFileName=1
>>"%SED%" echo InsideCompressed=0
>>"%SED%" echo CAB_FixedSize=0
>>"%SED%" echo RebootMode=N
>>"%SED%" echo TargetName=%ROOT%dist\ImageCompressor-Setup.exe
>>"%SED%" echo FriendlyName=Image Compressor Setup
>>"%SED%" echo AppLaunched=setup.cmd
>>"%SED%" echo PostInstallCmd=<None>
>>"%SED%" echo AdminQuietInstCmd=
>>"%SED%" echo UserQuietInstCmd=
>>"%SED%" echo SourceFiles=SourceFiles
>>"%SED%" echo [Strings]
>>"%SED%" echo [SourceFiles]
>>"%SED%" echo SourceFiles0=%STAGE%
>>"%SED%" echo [SourceFiles0]
>>"%SED%" echo %EXENAME%=
>>"%SED%" echo setup.cmd=
>>"%SED%" echo uninstall.cmd=

iexpress /N /Q "%SED%"
if errorlevel 1 ( echo [ERROR] iexpress failed. & pause & exit /b 1 )
if not exist "%ROOT%dist\ImageCompressor-Setup.exe" ( echo [ERROR] Setup exe was not created. & pause & exit /b 1 )

rem Clean up staging artifacts.
del /q "%SED%" 2>nul
rmdir /s /q "%STAGE%" 2>nul

echo.
echo ============================================
echo   Done! Setup: dist\ImageCompressor-Setup.exe
echo ============================================
echo.
pause
endlocal
