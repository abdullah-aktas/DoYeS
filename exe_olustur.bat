@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo DOSE Yonetim Sistemi - EXE paketi ve kurulum dosyasi olusturuluyor...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto hata

python -m unittest discover -s tests
if errorlevel 1 (
    echo Testler basarisiz; paketleme durduruldu.
    goto hata
)

python -m PyInstaller --noconfirm --clean --windowed --name DOSE_Yonetim ^
    --icon dose\gorsel\ikon.ico ^
    --add-data "dose\gorsel;dose\gorsel" ^
    --collect-submodules dose ^
    --hidden-import reportlab.graphics.barcode.common ^
    --collect-all psycopg ^
    --collect-all psycopg_binary ^
    main.py
if errorlevel 1 goto hata
if exist "dist\DOSE_Yonetim\veri" rmdir /s /q "dist\DOSE_Yonetim\veri"

rem Mobil sunucu programin MobilSunucu alt klasorune konur; ana klasordeki veri ve baglanti ayarini kullanir.
python -m PyInstaller --noconfirm --clean --console --name DOSE_Mobil_Sunucu ^
    --icon dose\gorsel\ikon.ico ^
    --add-data "dose\gorsel;dose\gorsel" ^
    --collect-submodules dose ^
    --collect-submodules sunucu ^
    --collect-submodules mobil ^
    --collect-submodules uvicorn ^
    --collect-all flet ^
    --collect-all flet_web ^
    --hidden-import reportlab.graphics.barcode.common ^
    --collect-all psycopg ^
    --collect-all psycopg_binary ^
    --exclude-module dose.ui ^
    --exclude-module PySide6 ^
    --exclude-module shiboken6 ^
    --exclude-module flet_desktop ^
    --distpath dist\mobil_sunucu ^
    sunucu_main.py
if errorlevel 1 goto hata
rem flet kancasi masaustu istemcisini de ekler; sunucu web arayuzu icin gerekmez.
if exist "dist\mobil_sunucu\DOSE_Mobil_Sunucu\_internal\flet_desktop" rmdir /s /q "dist\mobil_sunucu\DOSE_Mobil_Sunucu\_internal\flet_desktop"
if exist "dist\DOSE_Yonetim\MobilSunucu" rmdir /s /q "dist\DOSE_Yonetim\MobilSunucu"
xcopy /e /i /q /y "dist\mobil_sunucu\DOSE_Mobil_Sunucu" "dist\DOSE_Yonetim\MobilSunucu" >nul
if errorlevel 1 goto hata
if exist "mobil\DOSE_Mobil.apk" (
    if not exist "dist\DOSE_Yonetim\mobil" mkdir "dist\DOSE_Yonetim\mobil"
    copy /y "mobil\DOSE_Mobil.apk" "dist\DOSE_Yonetim\mobil\" >nul
)

echo.
echo Tamamlandi: dist\DOSE_Yonetim\DOSE_Yonetim.exe ve DOSE_Mobil_Sunucu.exe

for /f "delims=" %%v in ('python -c "from dose import SURUM; print(SURUM)"') do set SURUM=%%v
set ISCC=
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
    if exist %%p set ISCC=%%p
)
if not defined ISCC (
    echo.
    echo Inno Setup bulunamadi; kurulum dosyasi olusturulmadi.
    echo Kurmak icin: winget install JRSoftware.InnoSetup
    echo Simdilik dist\DOSE_Yonetim klasorunu kopyalayarak dagitabilirsiniz.
    pause
    exit /b 0
)
%ISCC% /Q /DAppVersion=%SURUM% kurulum.iss
if errorlevel 1 goto hata
echo.
echo Kurulum dosyasi: kurulum_paketi\DOSE_Yonetim_Kurulum_%SURUM%.exe
echo Bu tek dosyayi okullara gonderin; cift tiklayinca kurulum sihirbazi acilir.
pause
exit /b 0

:hata
echo Islem basarisiz oldu.
pause
exit /b 1
