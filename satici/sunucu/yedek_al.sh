#!/usr/bin/env bash
# Bütün okul veritabanlarının gecelik yedeği; 60 günden eski yedekler silinir.
# postgres kullanıcısının crontab'ına:  0 2 * * * /opt/dose/yedek_al.sh
set -euo pipefail

HEDEF="/var/backups/dose"
mkdir -p "$HEDEF"
for VT in $(psql -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'okul\_%'"); do
    pg_dump -Fc "$VT" > "$HEDEF/${VT}_$(date +%F).dump"
done
find "$HEDEF" -name '*.dump' -mtime +60 -delete
