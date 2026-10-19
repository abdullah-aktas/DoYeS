#!/usr/bin/env bash
# Çok okullu barındırma sunucusunda yeni okul için ayrı veritabanı ve kullanıcı açar.
# Kullanım:  sudo ./okul_ekle.sh 765432 ["Okul Adı"]
# Veritabanı adı ile kullanıcı adı aynıdır (okul_<kurum kodu>); pg_hba.conf'taki tek 'sameuser' satırı yeterlidir.
# Şifre veri/okullar.json (veya /opt/dose/okullar.json) dosyasına da yazılır — mobil geçit (--coklu) bunu okur.
set -euo pipefail

KOD="${1:-}"
AD="${2:-}"
if [[ ! "$KOD" =~ ^[0-9]{5,8}$ ]]; then
    echo "Kullanım: $0 <kurum kodu> [okul adı]   (kurum kodu yalnız rakam)" >&2
    exit 1
fi
AD_VT="okul_${KOD}"
SIFRE="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
OKULLAR_JSON="${DOSE_OKULLAR_JSON:-/opt/dose/okullar.json}"

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${AD_VT}'" | grep -q 1; then
    echo "${AD_VT} zaten var. Şifreyi yenilemek için: sudo -u postgres psql -c \"ALTER ROLE ${AD_VT} PASSWORD '...'\"" >&2
    exit 1
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE ${AD_VT} LOGIN PASSWORD '${SIFRE}' CONNECTION LIMIT 30;
CREATE DATABASE ${AD_VT} OWNER ${AD_VT} ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE ${AD_VT} FROM PUBLIC;
SQL

SUNUCU="$(hostname -f 2>/dev/null || hostname)"

# Mobil geçit için okullar.json güncelle (python3 varsa)
if command -v python3 >/dev/null 2>&1; then
    DOSE_OKUL_KOD="$KOD" DOSE_OKUL_AD="$AD" DOSE_OKUL_SIFRE="$SIFRE" DOSE_OKUL_VT="$AD_VT" \
    DOSE_PG_HOST="$SUNUCU" DOSE_OKULLAR_JSON="$OKULLAR_JSON" python3 <<'PY'
import json, os
from pathlib import Path
yol = Path(os.environ["DOSE_OKULLAR_JSON"])
yol.parent.mkdir(parents=True, exist_ok=True)
try:
    veri = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
except Exception:
    veri = {}
veri.setdefault("sunucu", os.environ.get("DOSE_PG_HOST", ""))
veri.setdefault("port", 5432)
veri.setdefault("ssl", "require")
veri.setdefault("okullar", {})
kod = os.environ["DOSE_OKUL_KOD"]
veri["okullar"][kod] = {
    "ad": os.environ.get("DOSE_OKUL_AD") or f"Kurum {kod}",
    "sifre": os.environ["DOSE_OKUL_SIFRE"],
    "kullanici": os.environ["DOSE_OKUL_VT"],
}
yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Mobil geçit kaydı güncellendi: {yol}")
PY
fi

cat <<BILGI

Okul eklendi. Okulun her bilgisayarında Giriş ekranı > Bağlantı ayarları > Merkezi sunucu:
  Kurum kodu    : ${KOD}   (Kurum kodundan doldur düğmesiyle okul_${KOD} yazılır)
  Sunucu adresi : ${SUNUCU}
  Port          : 5432
  Veritabanı    : ${AD_VT}
  Kullanıcı     : ${AD_VT}
  Şifre         : ${SIFRE}
  SSL           : Zorunlu

Mobil (her yerden): uygulamaya kurum kodu ${KOD} + kullanıcı + şifre;
  geçit adresi  : https://<sizin-mobil-alan-adiniz>  (DOSE_Mobil_Sunucu --coklu)

Bu bilgileri okulun bilişim sorumlusuna güvenli yoldan iletin (şifreyi e-postada düz metin olarak göndermeyin).
İlk bağlanışta tablolar kurulur ve 'admin / admin' kullanıcısı oluşur; okul hemen şifresini değiştirmelidir.
Kurum ve Görevliler sayfasında kurum kodunu ${KOD} yapıp lisansı etkinleştiriniz.
BILGI
