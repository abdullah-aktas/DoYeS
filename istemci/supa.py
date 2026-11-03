"""Minimal async Supabase client (Auth + PostgREST) that runs on desktop, Android and in the browser (Pyodide)."""
from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Awaitable, Callable

Tasima = Callable[[str, str, dict, bytes | None], Awaitable[tuple[int, str]]]

AUTH_MESAJLARI = {
    "invalid_credentials": "E-posta veya şifre hatalı.",
    "invalid_grant": "E-posta veya şifre hatalı.",
    "email_not_confirmed": "E-posta adresiniz doğrulanmamış. Gelen kutunuzdaki bağlantıya tıklayın.",
    "user_already_exists": "Bu e-posta adresiyle zaten hesap var. Giriş yapın veya şifrenizi sıfırlayın.",
    "email_exists": "Bu e-posta adresiyle zaten hesap var. Giriş yapın veya şifrenizi sıfırlayın.",
    "weak_password": "Şifre çok zayıf. En az 8 karakter; harf ve rakam kullanın.",
    "over_email_send_rate_limit": "Çok sık e-posta istendi. Birkaç dakika sonra yeniden deneyin.",
    "over_request_rate_limit": "Çok fazla deneme yapıldı. Birkaç dakika sonra yeniden deneyin.",
    "validation_failed": "E-posta adresi veya şifre biçimi geçersiz.",
    "signup_disabled": "Yeni hesap açma kapalı. Sistem yöneticinize başvurun.",
    "refresh_token_not_found": "Oturum süresi doldu. Yeniden giriş yapın.",
    "refresh_token_already_used": "Oturum süresi doldu. Yeniden giriş yapın.",
    "session_not_found": "Oturum süresi doldu. Yeniden giriş yapın.",
}


class SupaHata(Exception):
    def __init__(self, mesaj: str, durum: int = 0, kod: str | None = None, ipucu: str | None = None):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.durum = durum
        self.kod = kod
        self.ipucu = ipucu

    @property
    def cakisma(self) -> bool:
        return self.ipucu == "surum_cakismasi"

    @property
    def oturum_gecersiz(self) -> bool:
        return self.durum == 401 or self.kod in ("PGRST301", "PGRST303", "refresh_token_not_found",
                                                 "refresh_token_already_used", "session_not_found")


def hata_coz(durum: int, metin: str) -> SupaHata:
    try:
        veri = json.loads(metin) if metin else {}
    except ValueError:
        veri = {}
    if not isinstance(veri, dict):
        veri = {}
    kod = veri.get("error_code") or veri.get("code") or veri.get("error")
    kod = str(kod) if kod is not None else None
    mesaj = veri.get("message") or veri.get("msg") or veri.get("error_description") or ""
    if kod in AUTH_MESAJLARI:
        mesaj = AUTH_MESAJLARI[kod]
    elif "row-level security" in mesaj or "permission denied" in mesaj:
        mesaj = "Bu işlem için yetkiniz yok."
    elif kod == "23505":
        mesaj = "Bu bilgilerle kayıtlı başka bir kayıt var."
    elif kod in ("PGRST202", "PGRST205", "42883", "42P01"):
        mesaj = "Veritabanı kurulumu tamamlanmamış. Sistem yöneticisi 'supabase db push' ile güncellemeleri yüklemeli."
    elif kod in ("PGRST301", "PGRST303") or (durum == 401 and not mesaj):
        mesaj = "Oturum süresi doldu. Yeniden giriş yapın."
    elif durum >= 500 and not mesaj:
        mesaj = "Sunucu şu an yanıt vermiyor. Biraz sonra yeniden deneyin."
    return SupaHata(mesaj or f"İşlem tamamlanamadı (HTTP {durum}).", durum, kod, veri.get("hint"))


async def _tarayici_tasima(yontem: str, url: str, basliklar: dict, govde: bytes | None) -> tuple[int, str]:
    from pyodide.http import pyfetch  # type: ignore[import-not-found]
    yanit = await pyfetch(url, method=yontem, headers=basliklar, body=govde.decode() if govde is not None else None)
    return yanit.status, await yanit.string()


def _ssl_baglami():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL = None


def _urllib_istek(yontem: str, url: str, basliklar: dict, govde: bytes | None) -> tuple[int, str]:
    global _SSL
    if _SSL is None:
        _SSL = _ssl_baglami()
    istek = urllib.request.Request(url, data=govde, headers=basliklar, method=yontem)
    try:
        with urllib.request.urlopen(istek, timeout=30, context=_SSL) as yanit:
            return yanit.status, yanit.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


async def _yerel_tasima(yontem: str, url: str, basliklar: dict, govde: bytes | None) -> tuple[int, str]:
    try:
        return await asyncio.to_thread(_urllib_istek, yontem, url, basliklar, govde)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SupaHata("İnternet bağlantısı kurulamadı. Bağlantınızı kontrol edip yeniden deneyin.", 0, "ag") from e


def varsayilan_tasima() -> Tasima:
    return _tarayici_tasima if sys.platform == "emscripten" else _yerel_tasima


def filtre(deger: Any) -> str:
    if deger is None:
        return "is.null"
    if isinstance(deger, bool):
        return f"is.{str(deger).lower()}"
    return f"eq.{deger}"


class Supa:
    def __init__(self, url: str, anahtar: str, tasima: Tasima | None = None,
                 oturum_degisti: Callable[[dict | None], Awaitable[None]] | None = None):
        self.url = url.rstrip("/")
        self.anahtar = anahtar
        self.tasima = tasima or varsayilan_tasima()
        self.oturum: dict | None = None
        self.oturum_degisti = oturum_degisti
        self._kilit = asyncio.Lock()

    # ------------------------------------------------------------------ transport
    async def _gonder(self, yontem: str, yol: str, govde: Any = None, basliklar: dict | None = None,
                      yetkili: bool = True) -> Any:
        b = {"apikey": self.anahtar, "Content-Type": "application/json", "Accept": "application/json"}
        if yetkili:
            await self._taze_tut()
            if self.oturum:
                b["Authorization"] = f"Bearer {self.oturum['access_token']}"
        b.update(basliklar or {})
        veri = json.dumps(govde, ensure_ascii=False).encode("utf-8") if govde is not None else None
        durum, metin = await self.tasima(yontem, self.url + yol, b, veri)
        if durum >= 400:
            hata = hata_coz(durum, metin)
            if yetkili and hata.oturum_gecersiz and self.oturum:
                await self._oturumu_birak()
            raise hata
        return json.loads(metin) if metin else None

    async def _oturumu_ayarla(self, veri: dict) -> dict:
        if "expires_at" not in veri and "expires_in" in veri:
            veri["expires_at"] = int(time.time()) + int(veri["expires_in"])
        self.oturum = veri
        if self.oturum_degisti:
            await self.oturum_degisti(veri)
        return veri

    async def _oturumu_birak(self):
        self.oturum = None
        if self.oturum_degisti:
            await self.oturum_degisti(None)

    async def _taze_tut(self):
        if not self.oturum or self.oturum.get("expires_at", 0) - 60 > time.time():
            return
        async with self._kilit:
            if self.oturum and self.oturum.get("expires_at", 0) - 60 <= time.time():
                await self.yenile(self.oturum["refresh_token"])

    # ------------------------------------------------------------------ auth
    async def kaydol(self, eposta: str, sifre: str) -> dict:
        veri = await self._gonder("POST", "/auth/v1/signup", {"email": eposta.strip().lower(), "password": sifre},
                                  yetkili=False)
        if veri and veri.get("access_token"):
            await self._oturumu_ayarla(veri)
        return veri or {}

    async def giris(self, eposta: str, sifre: str) -> dict:
        veri = await self._gonder("POST", "/auth/v1/token?grant_type=password",
                                  {"email": eposta.strip().lower(), "password": sifre}, yetkili=False)
        return await self._oturumu_ayarla(veri)

    async def yenile(self, yenileme: str) -> dict:
        try:
            veri = await self._gonder("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": yenileme},
                                      yetkili=False)
        except SupaHata as e:
            if e.durum in (400, 401, 403):
                await self._oturumu_birak()
            raise
        return await self._oturumu_ayarla(veri)

    async def cikis(self):
        if self.oturum:
            try:
                await self._gonder("POST", "/auth/v1/logout")
            except SupaHata:
                pass
        await self._oturumu_birak()

    async def sifre_sifirla(self, eposta: str):
        await self._gonder("POST", "/auth/v1/recover", {"email": eposta.strip().lower()}, yetkili=False)

    async def dogrulama_gonder(self, eposta: str):
        await self._gonder("POST", "/auth/v1/resend", {"type": "signup", "email": eposta.strip().lower()},
                           yetkili=False)

    async def sifre_degistir(self, yeni: str):
        await self._gonder("PUT", "/auth/v1/user", {"password": yeni})

    # ------------------------------------------------------------------ PostgREST
    async def sec(self, tablo: str, *, secim: str = "*", sira: str | None = None, limit: int | None = None,
                  **esit: Any) -> list[dict]:
        p = [("select", secim)] + [(k, filtre(v)) for k, v in esit.items()]
        if sira:
            p.append(("order", sira))
        if limit:
            p.append(("limit", str(limit)))
        return await self._gonder("GET", f"/rest/v1/{tablo}?{urllib.parse.urlencode(p)}") or []

    async def ekle(self, tablo: str, veri: dict) -> dict:
        r = await self._gonder("POST", f"/rest/v1/{tablo}", veri, {"Prefer": "return=representation"})
        return r[0] if r else {}

    async def guncelle(self, tablo: str, veri: dict, **esit: Any) -> dict:
        p = urllib.parse.urlencode([(k, filtre(v)) for k, v in esit.items()])
        r = await self._gonder("PATCH", f"/rest/v1/{tablo}?{p}", veri, {"Prefer": "return=representation"})
        if not r:
            raise SupaHata("Kayıt bulunamadı veya bu işlem için yetkiniz yok.", 404)
        return r[0]

    async def sil(self, tablo: str, **esit: Any) -> None:
        p = urllib.parse.urlencode([(k, filtre(v)) for k, v in esit.items()])
        r = await self._gonder("DELETE", f"/rest/v1/{tablo}?{p}", None, {"Prefer": "return=representation"})
        if not r:
            raise SupaHata("Kayıt bulunamadı veya bu işlem için yetkiniz yok.", 404)

    async def rpc(self, ad: str, **parametreler: Any) -> Any:
        return await self._gonder("POST", f"/rest/v1/rpc/{ad}", parametreler)
