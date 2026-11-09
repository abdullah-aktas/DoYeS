"""DÖSE marka token’ları ve ortak Flet yüzey bileşenleri."""
from __future__ import annotations

from collections.abc import Sequence

import flet as ft

ANA_RENK = "#1f4e79"
ANA_KOYU = "#0d2c4a"
ANA_ACIK = "#2f6aa3"
MARKA_VURGU = "#d48f2a"
ZEMIN = "#f0f4f8"
YUZEY = "#ffffff"
KENAR = "#d7e0ea"
METIN = "#1a2332"
METIN_IKINCIL = "#5c6b7a"
SECILI_DOLGU = "#e8eef5"

GIRIS_GRADYANI = ft.LinearGradient(
    begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
    colors=[ANA_KOYU, ANA_RENK, ANA_ACIK])


def renk_semasi() -> ft.ColorScheme:
    return ft.ColorScheme(
        primary=ANA_RENK,
        on_primary="#ffffff",
        primary_container=SECILI_DOLGU,
        on_primary_container=ANA_KOYU,
        secondary=MARKA_VURGU,
        on_secondary="#1a1205",
        surface=YUZEY,
        on_surface=METIN,
        on_surface_variant=METIN_IKINCIL,
        outline=KENAR,
        surface_container_highest=ZEMIN,
        error="#b3261e",
        on_error="#ffffff",
    )


def uygulama_temasi() -> ft.Theme:
    return ft.Theme(color_scheme=renk_semasi(), visual_density=ft.VisualDensity.COMFORTABLE)


def yuzey_kart(*kontroller: ft.Control, padding: int = 20, genislik_kolon=None,
               bgcolor: str = YUZEY) -> ft.Container:
    return ft.Container(
        ft.Column(list(kontroller), spacing=12, tight=True,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        padding=padding, bgcolor=bgcolor, border_radius=16,
        border=ft.Border.all(1, KENAR),
        shadow=ft.BoxShadow(blur_radius=18, spread_radius=0, offset=ft.Offset(0, 4),
                            color=ft.Colors.with_opacity(0.08, "#000000")),
        col=genislik_kolon)


def giris_kart(*kontroller: ft.Control, genislik_kolon=None) -> ft.Container:
    return ft.Container(
        ft.Column(list(kontroller), spacing=14, tight=True,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        padding=28, bgcolor=YUZEY, border_radius=20,
        shadow=ft.BoxShadow(blur_radius=28, spread_radius=0, offset=ft.Offset(0, 8),
                            color=ft.Colors.with_opacity(0.22, "#000000")),
        col=genislik_kolon or {"xs": 12, "sm": 10, "md": 7, "lg": 5, "xl": 4})


def sayfa_baslik_satiri(baslik: str, aksiyonlar: Sequence[ft.Control] | None = None,
                        ikon=None) -> ft.Control:
    sol = [ft.Icon(ikon or ft.Icons.DASHBOARD_OUTLINED, color=ANA_RENK, size=26),
           ft.Text(baslik, size=22, weight=ft.FontWeight.BOLD, color=METIN, expand=True)]
    return ft.Container(
        ft.Row(sol + list(aksiyonlar or []), spacing=10,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(bottom=4))


def liste_satiri(baslik: str, alt: str = "", secili: bool = False, on_click=None,
                 trailing: ft.Control | None = None) -> ft.Control:
    return ft.Container(
        ft.Row([
            ft.Container(width=4, border_radius=4,
                         bgcolor=ANA_RENK if secili else ft.Colors.TRANSPARENT,
                         height=44),
            ft.Column([
                ft.Text(baslik, weight=ft.FontWeight.W_600 if secili else ft.FontWeight.W_500,
                        color=ANA_RENK if secili else METIN, size=14),
                ft.Text(alt, size=12, color=METIN_IKINCIL, visible=bool(alt)),
            ], spacing=2, expand=True),
            trailing or ft.Container(width=0),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        bgcolor=SECILI_DOLGU if secili else YUZEY,
        border=ft.Border.all(1, ANA_RENK if secili else KENAR),
        border_radius=12, ink=True, on_click=on_click, margin=ft.Margin.only(bottom=6))


def ozellik_satiri(ikon, metin: str, renk) -> ft.Control:
    return ft.Row([
        ft.Container(ft.Icon(ikon, color=ANA_RENK, size=20), bgcolor=renk, border_radius=12,
                     width=40, height=40, alignment=ft.Alignment.CENTER),
        ft.Text(metin, color="#ffffff", size=14, weight=ft.FontWeight.W_500),
    ], spacing=12)


def bilgi_karti(baslik: str, govde: ft.Control | str, ikon=None) -> ft.Control:
    icerik = govde if isinstance(govde, ft.Control) else ft.Text(govde, size=13, color=METIN_IKINCIL)
    return yuzey_kart(
        ft.Row([ft.Icon(ikon or ft.Icons.INFO_OUTLINE, color=ANA_RENK, size=20),
                ft.Text(baslik, weight=ft.FontWeight.BOLD, color=METIN)], spacing=8),
        icerik, padding=16)


def deneme_rozeti(metin: str = "1 ay ücretsiz deneme") -> ft.Container:
    return ft.Container(
        ft.Row([ft.Icon(ft.Icons.CARD_GIFTCARD, color="#5c3d0a", size=18),
                ft.Text(metin, weight=ft.FontWeight.BOLD, color="#5c3d0a", size=13)],
               spacing=6, tight=True),
        bgcolor="#f5c76a", border_radius=20,
        padding=ft.Padding.symmetric(horizontal=14, vertical=6))


def baslik(metin: str, boyut: int = 22) -> ft.Text:
    return ft.Text(metin, size=boyut, weight=ft.FontWeight.BOLD, color=METIN)


def aciklama(metin: str) -> ft.Text:
    return ft.Text(metin, size=13, color=METIN_IKINCIL)


def kpi_karti(etiket: str, deger: str, ikon, renk: str = ANA_RENK,
              genislik_kolon=None) -> ft.Control:
    return ft.Container(
        ft.Column([
            ft.Row([
                ft.Container(ft.Icon(ikon, color=renk, size=22),
                             bgcolor=ft.Colors.with_opacity(0.12, renk),
                             border_radius=12, width=40, height=40,
                             alignment=ft.Alignment.CENTER),
                ft.Text(etiket, size=12, color=METIN_IKINCIL, expand=True),
            ], spacing=10),
            ft.Text(deger, size=22, weight=ft.FontWeight.BOLD, color=METIN),
        ], spacing=10, tight=True),
        padding=18, bgcolor=YUZEY, border_radius=16,
        border=ft.Border.all(1, KENAR),
        shadow=ft.BoxShadow(blur_radius=14, spread_radius=0, offset=ft.Offset(0, 3),
                            color=ft.Colors.with_opacity(0.07, "#000000")),
        col=genislik_kolon or {"xs": 12, "sm": 6, "md": 4, "lg": 3})


def oran_cubugu(etiket: str, deger: float, maksimum: float, renk: str,
                sag_metin: str = "") -> ft.Control:
    oran = 0.0 if maksimum <= 0 else max(0.0, min(1.0, float(deger) / float(maksimum)))
    dolu = max(0, int(round(oran * 100)))
    bos = 100 - dolu
    cubuk = ft.Row(spacing=0, expand=True, tight=True)
    if dolu:
        cubuk.controls.append(ft.Container(expand=dolu, height=10, bgcolor=renk, border_radius=8))
    if bos:
        cubuk.controls.append(ft.Container(expand=bos, height=10))
    return ft.Column([
        ft.Row([
            ft.Text(etiket, size=13, color=METIN, expand=True),
            ft.Text(sag_metin or f"{deger:g}", size=13, weight=ft.FontWeight.W_600, color=METIN),
        ], spacing=8),
        ft.Container(cubuk, height=10, bgcolor=KENAR, border_radius=8,
                     clip_behavior=ft.ClipBehavior.HARD_EDGE),
    ], spacing=6, tight=True)


def kahraman_seridi(baslik_metin: str, alt: str) -> ft.Control:
    return ft.Container(
        ft.Column([
            ft.Text(baslik_metin, size=24, weight=ft.FontWeight.BOLD, color="#ffffff"),
            ft.Text(alt, size=14, color=ft.Colors.with_opacity(0.9, "#ffffff")),
        ], spacing=6, tight=True),
        padding=ft.Padding.symmetric(horizontal=22, vertical=20),
        border_radius=18,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
            colors=[ANA_KOYU, ANA_RENK, ANA_ACIK]),
        shadow=ft.BoxShadow(blur_radius=20, offset=ft.Offset(0, 6),
                            color=ft.Colors.with_opacity(0.18, ANA_KOYU)))
