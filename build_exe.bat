@echo off
REM Butuh Python 3 (centang Add to PATH). Installer butuh Inno Setup 6 (jrsoftware.org).
pip install pyinstaller
pyinstaller --onefile --noconsole --name AnugrahKeuangan anugrah_keuangan.py
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss
echo Installer: output\AnugrahKeuangan-Setup.exe
pause
