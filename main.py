from __future__ import annotations

import flet as ft

from app.config import APP_NAME, APP_VERSION, DEVICE_THEMES, resolve_device_theme
from app.database import initialize_schema
from app.ui.login_view import LoginView
from app.ui.dashboard_view import DashboardView


class DoseApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = f"{APP_NAME} v{APP_VERSION}"
        self.page.vertical_alignment = ft.MainAxisAlignment.CENTER
        self.page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.page.padding = 20
        self.page.bgcolor = "#f3f6fb"
        self.page.scroll = ft.ScrollMode.AUTO
        self.page.window_width = 1280
        self.page.window_height = 860
        self.page.window_min_width = 320
        self.page.window_min_height = 560
        self.page.on_resize = self.handle_resize
        self.session_username = None
        self.apply_device_theme()
        initialize_schema()
        self.show_login()

    def apply_device_theme(self):
        width = self.page.width or self.page.window_width or 1280
        device_type = resolve_device_theme(width)
        theme = DEVICE_THEMES[device_type]
        self.page.bgcolor = theme["bgcolor"]
        self.page.padding = theme["padding"]
        self.page.theme = ft.Theme(color_scheme_seed=theme["primary"])
        self.page.update()

    def handle_resize(self, e):
        self.apply_device_theme()
        for control in self.page.controls:
            if hasattr(control, "refresh_layout"):
                control.refresh_layout()
        self.page.update()

    def show_login(self):
        self.session_username = None
        self.page.controls.clear()
        self.page.add(LoginView(self))
        self.page.update()

    def show_dashboard(self, username: str):
        self.session_username = username
        self.page.controls.clear()
        self.page.add(DashboardView(self, username))
        self.page.update()


def main(page: ft.Page):
    DoseApp(page)


if __name__ == "__main__":
    ft.run(main)
