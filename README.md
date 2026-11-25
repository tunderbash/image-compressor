# Image Compressor

A small offline Windows desktop app for batch JPG/JPEG and PNG compression.

## Important behavior
- JPEG: keeps the original pixel dimensions and searches for the highest JPEG quality that fits the maximum size.
- PNG: uses lossless optimization only. Some PNGs (especially screenshots, graphics, and transparent images) may remain above the requested size. The app will not silently reduce their quality.
- Default target: 100 KB. If that cannot be reached, it tries the preferred 120 KB band, then the hard maximum of 150 KB.
- JPEG output uses the highest tested quality that fits the first achievable size band.
- Original files are never overwritten.

## Run from source
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run: `py -m pip install -r requirements.txt`
4. Run: `py main.py`

## Build a Windows executable and setup
Run `build_setup.bat`. It installs the dependencies, builds a **single-file**
executable, and packages an installer. Output:

- `dist\ImageCompressor.exe` — portable single-file app (just run it).
- `dist\ImageCompressor-Setup.exe` — installer: asks where to install, then
  creates Start Menu and Desktop shortcuts and registers the app in
  "Apps & Features".

To remove an installed copy, use "Apps & Features" (Uninstall) or run
`uninstall.cmd` inside the install folder.

> The setup is a self-extracting `.exe` (built with Windows IExpress), so it
> needs no administrator rights and no extra tools. A true `.msi` would require
> the WiX Toolset and admin rights; this `.exe` installer gives the same
> graphical experience without them.

## Notes
JPEG compression is lossy by nature. This app does not resize images. For JPEG files, the app tries to preserve the best quality it can while staying under the selected maximum. If the file cannot fit even at its lowest configured quality, it outputs the best attempt and reports its size.
