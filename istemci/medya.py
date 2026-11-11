"""Sesle / yapıştırarak metin girişi ve duyuru kapatma tercihleri."""
from __future__ import annotations

import flet as ft

DUYURU_OK_ANAHTAR = "dose.duyuru_okundu"


def duyuru_anahtar(uyg: dict | None) -> str:
    uyg = uyg or {}
    surum = (uyg.get("surum") or "").strip()
    duyuru = (uyg.get("duyuru") or "").strip()
    return f"{surum}|{duyuru}"


async def duyuru_okundu_mu(page: ft.Page, uyg: dict | None) -> bool:
    if not uyg or not (uyg.get("duyuru") or "").strip():
        # Yalnız sürüm farkı uyarısı da kapatılabilir
        if not uyg:
            return False
    try:
        kayit = await page.shared_preferences.get(DUYURU_OK_ANAHTAR)
    except Exception:
        return False
    return (kayit or "") == duyuru_anahtar(uyg)


async def duyuru_okundu_isaretle(page: ft.Page, uyg: dict | None):
    try:
        await page.shared_preferences.set(DUYURU_OK_ANAHTAR, duyuru_anahtar(uyg or {}))
    except Exception:
        pass


def ses_veya_metin_dialog(
    app,
    *,
    baslik: str = "Metin / sesle yaz",
    ipucu: str = "",
    baslangic: str = "",
    on_tamam=None,
):
    """Çok satırlı alan: Win+H dikte, yapıştırma veya (web) tarayıcı mikrofonu."""
    alan = ft.TextField(
        value=baslangic, multiline=True, min_lines=6, max_lines=14,
        hint_text=ipucu or "Başlık satırını ve verileri yazın / yapıştırın. Windows’ta Win+H ile dikte.",
        expand=True)
    durum = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

    async def tamam(_=None):
        metin = (alan.value or "").strip()
        if not metin:
            durum.value = "Metin boş."
            app.page.update()
            return
        app.page.pop_dialog()
        if on_tamam:
            await on_tamam(metin)

    async def mikrofon(_=None):
        """Tek cümlelik web SpeechRecognition; masaüstünde kullanıcıya Win+H hatırlatılır."""
        platform = (getattr(app.page, "platform", None) or "").lower()
        if platform and platform not in ("web",):
            # Flet masaüstü: sistem diktesi
            durum.value = "Masaüstünde alanı seçip Win+H (Windows dikte) kullanın."
            app.page.update()
            return
        try:
            js = """
(() => new Promise((resolve) => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { resolve({ok:false, hata:'Tarayıcı mikrofon tanımayı desteklemiyor.'}); return; }
  const r = new SR();
  r.lang = 'tr-TR'; r.interimResults = false; r.maxAlternatives = 1;
  r.onresult = (e) => resolve({ok:true, metin: e.results[0][0].transcript || ''});
  r.onerror = (e) => resolve({ok:false, hata: e.error || 'mikrofon'});
  r.onend = () => {};
  try { r.start(); } catch (err) { resolve({ok:false, hata: String(err)}); }
}))()
"""
            durum.value = "Dinleniyor… konuşun."
            app.page.update()
            sonuc = await app.page.run_javascript(js)
            if isinstance(sonuc, dict) and sonuc.get("ok") and sonuc.get("metin"):
                ek = str(sonuc["metin"]).strip()
                alan.value = ((alan.value or "").rstrip() + ("\n" if alan.value else "") + ek)
                durum.value = "Metin eklendi. Gerekirse düzenleyip Tamam’a basın."
            else:
                hata = (sonuc or {}).get("hata") if isinstance(sonuc, dict) else "sonuç yok"
                durum.value = f"Mikrofon: {hata}. Win+H veya yapıştırma kullanın."
        except Exception as e:
            durum.value = f"Mikrofon kullanılamadı ({e}). Win+H veya yapıştırma deneyin."
        app.page.update()

    try:
        from .tema import dialog_genislik
    except ImportError:
        from tema import dialog_genislik
    genislik = dialog_genislik(app.page, 520)
    app.page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text(baslik),
        content=ft.Column([alan, durum], tight=True, width=genislik, height=280),
        actions=[
            ft.TextButton("Mikrofon", icon=ft.Icons.MIC, on_click=lambda _: app.page.run_task(mikrofon)),
            ft.TextButton("Vazgeç", on_click=lambda _: app.page.pop_dialog()),
            ft.FilledButton("Tamam", icon=ft.Icons.CHECK, on_click=lambda _: app.page.run_task(tamam)),
        ]))
