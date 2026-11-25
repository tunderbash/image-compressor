@echo off
py -m pip install -r requirements.txt
py -m pip install pyinstaller
py -m PyInstaller --noconfirm --windowed --name ImageCompressor --onedir --collect-all PySide6 main.py
echo.
echo Build complete. See dist\ImageCompressor\ImageCompressor.exe
pause
