"""Flet istemcisini doğrudan bu klasörden çalıştırmak için (APK/web paketleme giriş noktası)."""
import os

import flet as ft

from uygulama import calistir

ft.run(calistir(), assets_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))
