"""DÖSE Flet masaüstü uygulamasının başlangıç noktası."""
import flet as ft

from istemci.uygulama import VARLIK_KLASORU, calistir


if __name__ == "__main__":
    ft.run(calistir(), assets_dir=VARLIK_KLASORU)
