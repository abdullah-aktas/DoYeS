# DÖSE kurum yayını: Windows + web (+ isteğe bağlı APK) paketlerini yayin/ altına üretir.
# Kullanım (depo kökünden):  powershell -ExecutionPolicy Bypass -File scripts\yayin_paketle.ps1
param(
    [switch]$Apk,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok

$Surum = (python -c "import tomllib; print(tomllib.load(open('istemci/pyproject.toml','rb'))['project']['version'])").Trim()
$Yayin = Join-Path $Kok "yayin\DOSE_$Surum"
# Kullanıcı yolunda boşluk (örn. "Muhasebe Ogretmenim") native asset derlemesini kırar.
$Stage = "C:\dose_build_stage"
$env:PUB_CACHE = "C:\pub-cache"
$env:HOME = "C:\dose_home"
$env:APPDATA = "C:\dose_home\AppData\Roaming"
$env:LOCALAPPDATA = "C:\dose_home\AppData\Local"
New-Item -ItemType Directory -Force -Path $env:PUB_CACHE, $env:APPDATA, $env:LOCALAPPDATA | Out-Null
if (Test-Path "C:\dev\flutter\bin") {
    $env:PATH = "C:\dev\flutter\bin;" + $env:PATH
}

Write-Host "Sürüm: $Surum"
Write-Host "Çıktı: $Yayin"
Write-Host "Sahne: $Stage (boşluksuz yol)"

if (-not $SkipTests) {
    Write-Host "`n=== Testler ==="
    Push-Location (Join-Path $Kok "supabase")
    npm test
    if ($LASTEXITCODE -ne 0) { throw "supabase npm test başarısız" }
    Pop-Location
    python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "pytest başarısız" }
}

Write-Host "`n=== Sahne klasörü ==="
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
robocopy (Join-Path $Kok "istemci") $Stage /E /XD __pycache__ build .dart_tool store android /XF DOSE_Mobil.apk *.aab /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "istemci kopyası başarısız" }
robocopy (Join-Path $Kok "dose") (Join-Path $Stage "dose") /E /XD __pycache__ /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "dose kopyası başarısız" }
if (Test-Path (Join-Path $Kok "istemci\android")) {
    robocopy (Join-Path $Kok "istemci\android") (Join-Path $Stage "android") /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
}

New-Item -ItemType Directory -Force -Path $Yayin | Out-Null
$env:PYTHONUTF8 = "1"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"

Write-Host "`n=== Windows ==="
Push-Location $Stage
flet build windows --yes
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Windows derlemesi başarısız" }
$WinZip = Join-Path $Yayin "DOSE_Yonetim_${Surum}_Windows.zip"
if (Test-Path $WinZip) { Remove-Item $WinZip -Force }
Compress-Archive -Path (Join-Path $Stage "build\windows\*") -DestinationPath $WinZip -Force
Write-Host "Windows zip: $WinZip"

Write-Host "`n=== Web ==="
flet build web --yes
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Web derlemesi başarısız" }
$WebZip = Join-Path $Yayin "DOSE_Yonetim_${Surum}_Web.zip"
if (Test-Path $WebZip) { Remove-Item $WebZip -Force }
Compress-Archive -Path (Join-Path $Stage "build\web\*") -DestinationPath $WebZip -Force
Write-Host "Web zip: $WebZip"
Pop-Location

if ($Apk) {
    Write-Host "`n=== APK (istemci\apk_aab_olustur.bat) ==="
    # Bat kendi sahnesinde dose kopyalamalı; güncel bat kullanılır
    Push-Location (Join-Path $Kok "istemci")
    cmd /c apk_aab_olustur.bat
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "APK derlemesi başarısız" }
    Pop-Location
    $ApkSrc = Join-Path $Kok "istemci\store\DOSE_Mobil_$Surum.apk"
    if (Test-Path $ApkSrc) {
        Copy-Item $ApkSrc (Join-Path $Yayin "DOSE_Mobil_$Surum.apk") -Force
    }
    $AabSrc = Join-Path $Kok "istemci\store\DOSE_Mobil_$Surum.aab"
    if (Test-Path $AabSrc) {
        Copy-Item $AabSrc (Join-Path $Yayin "DOSE_Mobil_$Surum.aab") -Force
    }
}

# Kuruma not
$Not = @"
# DÖSE Yönetim $Surum — Kurum teslim paketi

Üretim tarihi: $(Get-Date -Format 'yyyy-MM-dd HH:mm')
Canlı veritabanı: migrations güncel (supabase db push).

## Bu klasördeki dosyalar

| Dosya | Kuruma verin |
|---|---|
| DOSE_Yonetim_${Surum}_Windows.zip | Masaüstü: açıp çalıştırın |
| DOSE_Yonetim_${Surum}_Web.zip | Sizin HTTPS hostunuza yükleyin; kuruma URL verin |
| DOSE_Mobil_*.apk (varsa) | Android yan yükleme |
| DOSE_Mobil_*.aab (varsa) | Google Play |

## Her kurum için sizin yapmanız gerekenler

1. Supabase SQL Editor:

``````sql
select dose_private.okul_ac(
  'KURUMUN RESMİ ADI',
  'MEB_KURUM_KODU',
  date '2027-08-31',
  interval '7 days'
);
``````

2. Dönen ``DOSE-…`` kodunu güvenli kanalla müdüre verin.
3. Bu zip + [KURULUM](https://github.com/abdullah-aktas/DoYeS/blob/main/docs/KURULUM.md) linkini verin.
4. Destek iletişimini yazın.

Ayrıntı: docs/SATIS_VE_TESLIM.md
"@
Set-Content -Path (Join-Path $Yayin "KURUMA_TESLIM.md") -Value $Not -Encoding UTF8

Write-Host "`nTamam. Paket: $Yayin (sahne C:\dose_build_stage bırakıldı)"
Get-ChildItem $Yayin | Format-Table Name, Length -AutoSize
