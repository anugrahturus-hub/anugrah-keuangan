@echo off
REM Butuh Python 3 (centang Add to PATH). Tutup aplikasi Anugrah Keuangan sebelum menjalankan.
echo === 1. Membersihkan hasil build lama ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist AnugrahKeuangan.spec del AnugrahKeuangan.spec
echo === 2. Membuat AnugrahKeuangan.exe dari anugrah_keuangan.py ===
pip install pyinstaller
pyinstaller --onefile --noconsole --name AnugrahKeuangan anugrah_keuangan.py
if not exist dist\AnugrahKeuangan.exe goto gagal
echo === 3. Membuat installer ===
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 7\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" "%LocalAppData%\Programs\Inno Setup 7\ISCC.exe") do if exist %%P set "ISCC=%%~P"
if defined ISCC goto ada
echo Inno Setup tidak ditemukan otomatis. Buka installer.iss dengan Inno Setup lalu tekan Ctrl+F9.
goto selesai
:ada
"%ISCC%" installer.iss
echo Installer ada di folder output.
goto selesai
:gagal
echo GAGAL membuat exe. Kirim tampilan error di atas.
:selesai
pause
