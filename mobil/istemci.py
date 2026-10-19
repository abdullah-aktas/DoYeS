"""DÖSE Mobil sunucusuna bağlanan HTTP istemcisi (yalnız standart kütüphane; Android'de de çalışır)."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request


class ApiHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 0):
        super().__init__(mesaj)
        self.kod = kod


def _ssl_baglami(dogrula: bool) -> ssl.SSLContext:
    if not dogrula:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def adres_duzelt(adres: str) -> str:
    """'192.168.1.10' -> 'http://192.168.1.10:8765'; https adreslerinde port verilmezse 443 kullanılır."""
    adres = (adres or "").strip().rstrip("/")
    if adres and "://" not in adres:
        adres = "http://" + adres
    p = urllib.parse.urlsplit(adres)
    if adres and p.scheme == "http" and p.port is None:
        adres = f"http://{p.hostname}:8765{p.path}"
    return adres


class Istemci:
    def __init__(self, adres: str, sertifika_dogrula: bool = True, ek_basliklar: dict | None = None):
        self.adres = adres_duzelt(adres)
        self.token: str | None = None
        self.ssl = _ssl_baglami(sertifika_dogrula)
        self.ek_basliklar = ek_basliklar or {}

    def istek(self, yontem: str, yol: str, veri: dict | None = None, **sorgu):
        sorgu = {k: v for k, v in sorgu.items() if v not in (None, "")}
        url = self.adres + "/api" + yol + ("?" + urllib.parse.urlencode(sorgu) if sorgu else "")
        govde = json.dumps(veri).encode("utf-8") if veri is not None else None
        basliklar = {"Accept": "application/json", **self.ek_basliklar}
        if govde is not None:
            basliklar["Content-Type"] = "application/json"
        if self.token:
            basliklar["Authorization"] = "Bearer " + self.token
        r = urllib.request.Request(url, data=govde, method=yontem, headers=basliklar)
        try:
            with urllib.request.urlopen(r, timeout=25, context=self.ssl if url.startswith("https") else None) as y:
                icerik = y.read()
        except urllib.error.HTTPError as e:
            try:
                mesaj = json.loads(e.read().decode("utf-8")).get("hata")
            except Exception:
                mesaj = None
            raise ApiHatasi(mesaj or f"Sunucu hatası ({e.code}).", e.code) from None
        except ssl.SSLError as e:
            raise ApiHatasi(f"Güvenli bağlantı kurulamadı: {e.reason or e}. Sunucu sertifikasını kontrol ediniz.") from None
        except (urllib.error.URLError, OSError) as e:
            neden = getattr(e, "reason", e)
            raise ApiHatasi(f"Sunucuya ulaşılamıyor ({self.adres}). Adresi, Wi-Fi bağlantısını ve sunucunun açık "
                            f"olduğunu kontrol ediniz.\n\nAyrıntı: {neden}") from None
        return json.loads(icerik.decode("utf-8")) if icerik else {}

    def get(self, yol: str, **sorgu):
        return self.istek("GET", yol, **sorgu)

    def post(self, yol: str, veri: dict | None = None):
        return self.istek("POST", yol, veri or {})

    def put(self, yol: str, veri: dict):
        return self.istek("PUT", yol, veri)

    def delete(self, yol: str, **sorgu):
        return self.istek("DELETE", yol, **sorgu)

    def giris(self, kullanici_adi: str, sifre: str, cihaz: str, kurum_kodu: str = "") -> dict:
        self.token = None
        govde = {"kullanici_adi": kullanici_adi, "sifre": sifre, "cihaz": cihaz}
        if kurum_kodu:
            govde["kurum_kodu"] = "".join(str(kurum_kodu).split())
        y = self.post("/giris", govde)
        self.token = y["token"]
        return y

    def kesif(self, kurum_kodu: str) -> dict:
        return self.post("/kesif", {"kurum_kodu": "".join(str(kurum_kodu).split())})

    @staticmethod
    def yol(*parcalar) -> str:
        return "/" + "/".join(urllib.parse.quote(str(p), safe="") for p in parcalar)
