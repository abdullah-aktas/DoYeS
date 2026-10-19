"""DÖSE Yönetim Mobil Sunucu.

Okulun sunucusunda veya sürekli açık bir bilgisayarda, masaüstü programın kurulu olduğu klasörden çalıştırılır;
programla aynı veritabanını (veri/dose.db veya baglanti.json'daki PostgreSQL) kullanır. Telefonlar ve tarayıcılar
bu servise bağlanır.

Çok okullu barındırmada (--coklu) veri/okullar.json üzerinden kurum koduna göre okul_<kod> veritabanına yönlendirir;
kullanıcılar her yerden yalnız kurum kodu + kullanıcı + şifre ile giriş yapar.

    DOSE_Mobil_Sunucu.exe [--port 8765] [--sertifika sunucu.crt --anahtar sunucu.key] [--veritabani yol]
    DOSE_Mobil_Sunucu.exe --coklu [--port 8765] [--sertifika ... --anahtar ...]
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and Path(sys.executable).parent.name == "MobilSunucu":
    # Kurulumda sunucu programın alt klasöründedir; veri ve bağlantı ayarı ana program klasöründen okunur.
    os.environ.setdefault("DOSE_KOK", str(Path(sys.executable).resolve().parent.parent))


def yerel_adresler() -> list[str]:
    adresler = set()
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            adresler.add(bilgi[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            adresler.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(a for a in adresler if not a.startswith("127."))


def main():
    from dose import SURUM
    from dose.lisans import SATICI

    ap = argparse.ArgumentParser(description="DÖSE Yönetim mobil erişim sunucusu")
    ap.add_argument("--host", default="0.0.0.0", help="Dinlenecek adres (varsayılan: bütün ağ kartları)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--veritabani", help="SQLite dosyası (verilmezse programın bağlantı ayarı kullanılır)")
    ap.add_argument("--sertifika", help="HTTPS için sertifika dosyası (.crt/.pem)")
    ap.add_argument("--anahtar", help="HTTPS için özel anahtar dosyası (.key)")
    ap.add_argument("--web-kapali", action="store_true", help="Tarayıcıdan erişilen web arayüzünü kapatır (yalnız API)")
    ap.add_argument("--coklu", action="store_true",
                    help="Çok okullu geçit: veri/okullar.json ile kurum koduna göre yönlendirir")
    a = ap.parse_args()

    import logging

    import uvicorn

    from dose import ag
    from dose import db as dbm

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from sunucu.api import uygulama_olustur

    sema = "https" if a.sertifika else "http"
    havuz = None
    if a.coklu:
        from sunucu.coklu import OkulHavuzu
        havuz = OkulHavuzu()
        app = uygulama_olustur(None, None if a.web_kapali else f"{sema}://127.0.0.1:{a.port}", havuz=havuz)
        print(f"DÖSE Yönetim Mobil Geçit {SURUM} — {SATICI} (çok okullu)")
        print(f"Okul kaydı: {ag.OKULLAR_DOSYASI} ({len((havuz.cfg.get('okullar') or {}))} okul)")
        print("Telefondaki uygulamaya: kurum kodu + kullanıcı + şifre yazınız.")
        print("Geçit adresi olarak şunlardan birini (veya alan adınızı) kullanınız:")
    else:
        app = uygulama_olustur(a.veritabani, None if a.web_kapali else f"{sema}://127.0.0.1:{a.port}")
        print(f"DÖSE Yönetim Mobil Sunucu {SURUM} — {SATICI}")
        print(f"Veritabanı: {dbm.al().aciklama()}")
        kod = __import__("dose.lisans", fromlist=["kurum_kodu_normalize"]).kurum_kodu_normalize(
            dbm.al().kurum().get("kurum_kodu"))
        if kod:
            print(f"Kurum kodu: {kod} (mobil girişte bu kodu kullanınız)")
        print("Telefondaki uygulamaya sunucu adresi olarak şunlardan birini yazınız:")
    for ip in yerel_adresler() or ["127.0.0.1"]:
        print(f"    {sema}://{ip}:{a.port}")
    if not a.web_kapali:
        print("Aynı adres bilgisayar veya telefon tarayıcısında açılınca web arayüzü gelir (kurulum gerekmez).")
    if not a.sertifika:
        print("UYARI: HTTPS kapalı. Okul dışından (internet üzerinden) erişim açılacaksa --sertifika ve --anahtar ile "
              "HTTPS kullanınız veya sunucuyu VPN arkasında tutunuz.")
    if not a.coklu:
        print("LAN keşif açık: aynı Wi-Fi'deki telefonlar sunucu adresini yazmadan bulabilir.")
    print("Durdurmak için bu pencereyi kapatınız veya Ctrl+C'ye basınız.")

    yayinci = None
    if not a.coklu:
        from dose.kesif import Yayinci
        from dose.lisans import kurum_kodu_normalize
        k = dbm.al().kurum()
        yayinci = Yayinci(port=a.port, https=bool(a.sertifika),
                          kurum_kodu=kurum_kodu_normalize(k.get("kurum_kodu")),
                          okul=k.get("okul_adi") or "")
        yayinci.baslat()

    try:
        uvicorn.run(app, host=a.host, port=a.port, ssl_certfile=a.sertifika, ssl_keyfile=a.anahtar,
                    log_level="warning", access_log=False)
    finally:
        if yayinci:
            yayinci.durdur()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
