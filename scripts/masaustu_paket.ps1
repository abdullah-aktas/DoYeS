# Kuruma verilebilir masaüstü paket (Python + Flet; native .exe değil).
# Depo kökünden: powershell -ExecutionPolicy Bypass -File scripts\masaustu_paket.ps1
$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
$Surum = (python -c "import tomllib; print(tomllib.load(open(r'$Kok\istemci\pyproject.toml','rb'))['project']['version'])").Trim()
$OutDir = Join-Path $Kok "yayin\DOSE_$Surum"
$Stage = Join-Path $OutDir "_masaustu_src"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

robocopy (Join-Path $Kok "istemci") (Join-Path $Stage "istemci") /E /XD __pycache__ build .dart_tool store android /XF DOSE_Mobil.apk *.aab signing.env *.p12 *.jks /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
robocopy (Join-Path $Kok "dose") (Join-Path $Stage "dose") /E /XD __pycache__ /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
Copy-Item (Join-Path $Kok "main.py") $Stage
Copy-Item (Join-Path $Kok "requirements.txt") $Stage

@'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Python 3.10+ bulunamadi. https://www.python.org/downloads/ adresinden kurun.
  echo Kurulumda "Add python.exe to PATH" secili olsun.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Ilk kurulum: sanal ortam ve paketler...
  python -m venv .venv || exit /b 1
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt || exit /b 1
) else (
  call .venv\Scripts\activate.bat
)
echo DÖSE Yönetim baslatiliyor...
python main.py
'@ | Set-Content -Path (Join-Path $Stage "DOSE_Baslat.bat") -Encoding ASCII

@'
# DÖSE Yönetim — Masaüstü paket (kurum)

## Gereksinim
- Windows 10/11
- Python 3.10 veya üstü (https://www.python.org/downloads/ — PATH’e ekleyin)

## Çalıştırma
1. Bu klasörü bilgisayara kopyalayın (Örn. `C:\DOSE`).
2. `DOSE_Baslat.bat` dosyasına çift tıklayın.
3. İlk açılışta paketler indirilir; sonraki açılışlar hızlıdır.

## İlk kullanım (müdür)
1. Hesap aç → e-posta doğrula → giriş.
2. Satıcının verdiği etkinleştirme kodu + MEB kurum kodu ile okulu bağlayın.
3. Kullanıcıları davet edin; tanımları girin.

Ayrıntı: https://github.com/abdullah-aktas/DoYeS/blob/main/docs/KURULUM.md

Bu paket GİB e-Fatura gönderimi veya banka API’si içermez.
'@ | Set-Content -Path (Join-Path $Stage "OKU.txt") -Encoding UTF8

$Zip = Join-Path $OutDir "DOSE_Yonetim_${Surum}_Masaustu.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Zip -Force
Remove-Item -Recurse -Force $Stage
Write-Host "Masaüstü paket: $Zip"
Get-Item $Zip | Format-List FullName, Length
