from __future__ import annotations

import flet as ft

from app.auth import validate_credentials


class LoginView(ft.Column):
    def __init__(self, app):
        self.app = app
        self.form_container = ft.Container(
            expand=True,
            width=420,
            padding=18,
            border_radius=18,
            bgcolor="white",
            border=ft.border.all(1, "#dee7f2"),
            content=ft.Column(
                spacing=18,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[],
            ),
        )
        self.username = ft.TextField(label="Kullanıcı adı", autofocus=True)
        self.password = ft.TextField(label="Şifre", password=True, can_reveal_password=True)
        self.message = ft.Text(value="", color="red")
        self.login_button = ft.ElevatedButton(
            "Giriş yap",
            icon=ft.Icons.LOGIN_ROUNDED,
            on_click=self.handle_login,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        )
        self.form_container.content.controls = [
            ft.Icon(icon=ft.Icons.SCHOOL_ROUNDED, size=54, color="#1f4e78"),
            ft.Text(value="DÖSE Yönetim", size=28, weight=ft.FontWeight.BOLD),
            ft.Text(value="Güvenli erişim paneli", size=14, color="#5a6474"),
            self.username,
            self.password,
            self.message,
            self.login_button,
            ft.TextButton("Bağlantı ayarları", on_click=lambda e: None),
        ]
        super().__init__(
            spacing=18,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.form_container],
        )
        self.refresh_layout()

    def refresh_layout(self):
        page_width = self.app.page.width or self.app.page.window_width or 420
        form_width = min(420, max(280, page_width - 28))
        self.form_container.width = form_width
        self.username.width = form_width - 24
        self.password.width = form_width - 24
        self.login_button.width = form_width - 24

    def handle_login(self, e):
        username = self.username.value.strip()
        password = self.password.value.strip()
        ok, result = validate_credentials(username, password)
        if not ok:
            self.message.value = result
            self.message.visible = True
            self.app.page.update()
            return

        self.message.value = ""
        self.app.show_dashboard(username)
