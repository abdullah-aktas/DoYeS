@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem DÖSE Mobil — imzalı APK (yan yükleme) + AAB (Google Play)
rem iOS IPA: yalnız macOS + Xcode ile (asagidaki nota bakin)
rem Imza: android\signing.env  (ornek: signing.env.example)

if not exist "android\signing.env" (
    echo Imza dosyasi yok: mobil\android\signing.env
    echo Ornek: copy android\signing.env.example android\signing.env
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("android\signing.env") do (
    if not "%%A"=="" set "%%A=%%B"
)

if "%ANDROID_HOME%"=="" set "ANDROID_HOME=C:\AndroidSdk"
if "%FLUTTER_ROOT%"=="" set "FLUTTER_ROOT=C:\flutter\3.41.4"
if "%PUB_CACHE%"=="" set "PUB_CACHE=C:\pub-cache"
if "%JAVA_HOME%"=="" set "JAVA_HOME=C:\Users\Muhasebe Ogretmenim\java\17.0.13+11"

set "PATH=%FLUTTER_ROOT%\bin;C:\Program Files\Git\cmd;%JAVA_HOME%\bin;%ANDROID_HOME%\platform-tools;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "FLET_CLI_NO_RICH_OUTPUT=1"
set "GRADLE_OPTS=-Dorg.gradle.daemon=false"

set "BUILD_SRC=C:\dose_mobil"
echo Kaynak kopyalaniyor -^> %BUILD_SRC%
if exist "%BUILD_SRC%" rmdir /s /q "%BUILD_SRC%" 2>nul
mkdir "%BUILD_SRC%" 2>nul
robocopy "%cd%" "%BUILD_SRC%" /E /XD __pycache__ build .dart_tool store /XF DOSE_Mobil.apk *.aab /NFL /NDL /NJH /NJS /nc /ns /np
if errorlevel 8 goto hata

rem Mutlak keystore yolu (Gradle goreli yolu yanlis cozer)
set "FLET_ANDROID_SIGNING_KEY_STORE=%BUILD_SRC%\android\upload-keystore.p12"
if not exist "%FLET_ANDROID_SIGNING_KEY_STORE%" (
    echo Keystore yok: %FLET_ANDROID_SIGNING_KEY_STORE%
    exit /b 1
)

cd /d "%BUILD_SRC%"

for /f "delims=" %%V in ('python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"') do set SURUM=%%V
for /f "delims=" %%N in ('python -c "v='%SURUM%'.split('.'); print(int(v[0])*10000+int(v[1])*100+int(v[2]))"') do set BUILD_NO=%%N
echo Surum %SURUM%  build-number %BUILD_NO%

echo.
echo === APK ===
flet build apk --yes --build-number %BUILD_NO% --build-version %SURUM% ^
  --android-signing-key-store "%FLET_ANDROID_SIGNING_KEY_STORE%" ^
  --android-signing-key-store-password "%FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD%" ^
  --android-signing-key-password "%FLET_ANDROID_SIGNING_KEY_PASSWORD%" ^
  --android-signing-key-alias "%FLET_ANDROID_SIGNING_KEY_ALIAS%"
if errorlevel 1 goto hata

echo.
echo === AAB (Google Play) ===
flet build aab --yes --build-number %BUILD_NO% --build-version %SURUM% ^
  --android-signing-key-store "%FLET_ANDROID_SIGNING_KEY_STORE%" ^
  --android-signing-key-store-password "%FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD%" ^
  --android-signing-key-password "%FLET_ANDROID_SIGNING_KEY_PASSWORD%" ^
  --android-signing-key-alias "%FLET_ANDROID_SIGNING_KEY_ALIAS%"
if errorlevel 1 goto hata

set "OUT=%~dp0store"
if not exist "%OUT%" mkdir "%OUT%"
for %%F in (build\apk\*.apk) do copy /y "%%F" "%~dp0DOSE_Mobil.apk" >nul & copy /y "%%F" "%OUT%\DOSE_Mobil_%SURUM%.apk" >nul
for %%F in (build\aab\*.aab) do copy /y "%%F" "%OUT%\DOSE_Mobil_%SURUM%.aab" >nul

echo.
echo Tamamlandi:
dir /b "%~dp0DOSE_Mobil.apk" "%OUT%\DOSE_Mobil_%SURUM%.*"
echo.
echo Google Play: store\DOSE_Mobil_%SURUM%.aab yukleyin.
echo iOS: Bu Windows PC'de IPA uretilemez. Mac'te ayni kaynakla:
echo   flet build ipa --yes --build-number %BUILD_NO% --build-version %SURUM%
echo   (Apple Developer team_id + sertifika gerekir; pyproject.toml [tool.flet.ios])
echo.
exit /b 0

:hata
echo Derleme basarisiz.
exit /b 1
