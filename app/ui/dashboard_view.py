from __future__ import annotations

import flet as ft

from app.auth import get_role_permissions, user_has_access
from app.database import add_audit_log, get_dashboard_summary, get_user
from app.ui.approvals_view import ApprovalsView
from app.ui.audit_view import AuditView
from app.ui.order_view import OrderView
from app.ui.personnel_view import PersonnelView
from app.ui.reports_view import ReportsView
from app.ui.student_view import StudentView


class DashboardView(ft.Column):
    def __init__(self, app, username: str):
        self.app = app
        self.username = username
        self.user_data = get_user(username) or {"role": "izleyici", "full_name": username}
        self.role = self.user_data.get("role", "izleyici")
        self.allowed_features = get_role_permissions(self.role)
        self.mobile_layout = False
        self.content_area = ft.Container(expand=True, padding=10)

        self.navigation_buttons = ft.Wrap(run_spacing=10, spacing=10)
        self.navigation = ft.ExpansionTile(
            title="İşlemler menüsü",
            leading=ft.Icons.MENU_ROUNDED,
            expanded=False,
            controls=[self.navigation_buttons],
            tile_padding=ft.padding.symmetric(horizontal=12, vertical=4),
            controls_padding=ft.padding.all(8),
            bgcolor="#ffffff",
            collapsed_bgcolor="#ffffff",
        )
        self.quick_cards = ft.Wrap(run_spacing=12, spacing=12)
        self._build_navigation()

        self.people_view = PersonnelView()
        self.approvals_view = ApprovalsView(username, self.role)
        self.order_view = OrderView(username=username)
        self.student_view = StudentView()
        self.reports_view = ReportsView()
        self.audit_view = AuditView()

        super().__init__(
            expand=True,
            spacing=20,
            controls=[
                ft.AppBar(
                    leading=ft.IconButton(ft.Icons.MENU_ROUNDED, tooltip="Menüyü aç/kapat", on_click=self.toggle_navigation),
                    title=ft.Text("DÖSE Yönetim"),
                    bgcolor="#1f4e78",
                    color="white",
                    center_title=self.mobile_layout,
                    actions=[
                        ft.IconButton(ft.Icons.NOTIFICATIONS_OUTLINED, tooltip="Bildirimler"),
                        ft.IconButton(ft.Icons.LOGOUT_ROUNDED, tooltip="Çıkış", on_click=self.logout),
                    ],
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(f"Hoş geldiniz, {self.user_data.get('full_name', username)}", size=26, weight=ft.FontWeight.BOLD),
                            ft.Container(content=ft.Text(f"Rol: {self.role}", color="#1f4e78"), padding=8),
                        ],
                        spacing=6,
                    ),
                    padding=10,
                ),
                self.navigation,
                self.content_area,
            ],
        )
        self.refresh_layout()
        self.show_dashboard()

    def refresh_layout(self):
        page_width = self.app.page.width or self.app.page.window_width or 1280
        self.mobile_layout = page_width < 700
        self.content_area.padding = 6 if self.mobile_layout else 10
        for button in self.navigation_buttons.controls:
            button.width = 150 if not self.mobile_layout else 120
        if hasattr(self, "_dashboard_grid"):
            self._dashboard_grid.runs_count = 2 if self.mobile_layout else 4
        if self.mobile_layout:
            self.quick_cards.visible = True
            self.quick_cards.run_spacing = 10
            self.quick_cards.spacing = 10
        else:
            self.quick_cards.visible = True

    def _build_navigation(self):
        nav_map = {
            "dashboard": ("Ana pano", ft.Icons.DASHBOARD_ROUNDED),
            "personnel": ("Personel", ft.Icons.PERSON_ROUNDED),
            "approvals": ("Onaylar", ft.Icons.CHECKLIST_ROUNDED),
            "orders": ("Sipariş", ft.Icons.ADD_SHOPPING_CART_ROUNDED),
            "students": ("Öğrenci", ft.Icons.SCHOOL_ROUNDED),
            "reports": ("Raporlar", ft.Icons.BAR_CHART_ROUNDED),
            "audit": ("Denetim", ft.Icons.INSIGHTS_ROUNDED),
        }
        controls = []
        for feature, (label, icon) in nav_map.items():
            if feature in self.allowed_features:
                controls.append(
                    ft.ElevatedButton(label, icon=icon, data=feature, on_click=self.handle_navigation)
                )
        self.navigation_buttons.controls = controls

    def toggle_navigation(self, e):
        self.navigation.expanded = not self.navigation.expanded
        self.update()

    def _require_access(self, feature: str, title: str):
        if not user_has_access(self.username, feature):
            self.content_area.content = ft.Column([
                ft.Text(title, size=24, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Text("Bu alana erişim yetkiniz yok. Lütfen yöneticinizle görüşün.", color="#d32f2f"),
                    padding=16,
                    border_radius=12,
                    bgcolor="#fff0f0",
                ),
            ])
            self.update()
            return False
        return True

    def handle_navigation(self, e):
        target = getattr(e.control, "data", "dashboard")
        if target == "dashboard":
            self.show_dashboard()
        elif target == "personnel":
            self.show_personnel()
        elif target == "approvals":
            self.show_approvals()
        elif target == "orders":
            self.show_order()
        elif target == "students":
            self.show_students()
        elif target == "reports":
            self.show_reports()
        elif target == "audit":
            self.show_audit()

    def card(self, title, value, color):
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(title, size=14, color="#5a6474"),
                    ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=color),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=220,
            height=120,
            padding=20,
            border_radius=14,
            bgcolor="#f4f7fb",
            border=ft.border.all(1, "#e8edf3"),
        )

    def _quick_action_card(self, title: str, icon: str, target: str):
        card = ft.Container(
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(name=icon, size=28, color="#1f4e78"),
                    ft.Text(title, size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                ],
            ),
            data=target,
            width=150 if self.mobile_layout else 170,
            height=90,
            padding=12,
            border_radius=14,
            bgcolor="#ffffff",
            border=ft.border.all(1, "#dfeaf5"),
            ink=True,
            on_click=self.handle_navigation,
        )
        return card

    def show_dashboard(self):
        summary = get_dashboard_summary()
        self._dashboard_grid = ft.GridView(
            expand=1,
            runs_count=2 if self.mobile_layout else 4,
            max_extent=260,
            child_aspect_ratio=1.5,
            spacing=15,
            run_spacing=15,
            controls=[
                self.card("Bekleyen onaylar", str(summary["pending_approvals"]), "#1f4e78"),
                self.card("Devamsızlık uyarıları", str(summary["warning_attendance"]), "#f9a825"),
                self.card("Kayıtlı öğrenciler", str(summary["student_count"]), "#2e7d32"),
                self.card("Not kayıtları", str(summary["grade_count"]), "#5a6474"),
            ],
        )
        action_map = [
            ("Sipariş / İş emri", ft.Icons.ADD_SHOPPING_CART_ROUNDED, "orders"),
            ("Öğrenci takibi", ft.Icons.SCHOOL_ROUNDED, "students"),
            ("Onay bekleyenler", ft.Icons.CHECKLIST_ROUNDED, "approvals"),
            ("Raporlar", ft.Icons.BAR_CHART_ROUNDED, "reports"),
            ("Denetim", ft.Icons.INSIGHTS_ROUNDED, "audit"),
        ]
        quick_controls = []
        for title, icon, target in action_map:
            if target in self.allowed_features or (target == "audit" and self.role in {"admin", "mudur", "mudur_yardimcisi"}):
                quick_controls.append(self._quick_action_card(title, icon, target))
        self.quick_cards.controls = quick_controls
        self.content_area.content = ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text(
                        "İşlem yapmadan önce okulunuzun güncel yetki devri ve yürürlükteki resmi usulünü kontrol edin. Bu ekranlar kontrol listesi sunar; mevzuat görüşü veya otomatik uygunluk kararı değildir.",
                        color="#664d03",
                    ),
                    padding=12,
                    bgcolor="#fff4cc",
                    border=ft.border.all(1, "#e7cf78"),
                    border_radius=8,
                ),
                self._dashboard_grid,
                ft.Text("Hızlı erişim", size=18, weight=ft.FontWeight.BOLD),
                self.quick_cards,
            ],
        )
        self.update()

    def show_personnel(self):
        if not self._require_access("personnel", "Personel"):
            return
        self.content_area.content = self.people_view
        self.update()

    def show_approvals(self):
        if not self._require_access("approvals", "Onaylar"):
            return
        self.content_area.content = self.approvals_view
        self.update()

    def show_order(self):
        if not self._require_access("orders", "Sipariş / İş emri"):
            return
        self.content_area.content = self.order_view
        self.update()

    def show_students(self):
        if not self._require_access("students", "Öğrenci takibi"):
            return
        self.content_area.content = self.student_view
        self.update()

    def show_reports(self):
        if not self._require_access("reports", "Raporlar"):
            return
        self.content_area.content = self.reports_view
        self.update()

    def show_audit(self):
        if self.role not in {"admin", "mudur", "mudur_yardimcisi"}:
            self.content_area.content = ft.Column([
                ft.Text("Denetim", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(content=ft.Text("Bu ekrana erişim yetkiniz yok.", color="#d32f2f"), padding=16, border_radius=12, bgcolor="#fff0f0"),
            ])
            self.update()
            return
        self.content_area.content = self.audit_view
        self.update()

    def logout(self, e):
        self.logout_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Güvenli çıkış"),
            content=ft.Text("Oturumu kapatıp giriş ekranına dönmek istiyor musunuz?"),
            actions=[
                ft.TextButton("Vazgeç", on_click=self.cancel_logout),
                ft.ElevatedButton("Çıkış yap", icon=ft.Icons.LOGOUT_ROUNDED, on_click=self.confirm_logout),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.app.page.show_dialog(self.logout_dialog)

    def cancel_logout(self, e):
        self.app.page.pop_dialog()

    def confirm_logout(self, e):
        add_audit_log("logout", "Kullanıcı güvenli şekilde oturumu kapattı", self.username)
        self.app.page.pop_dialog()
        self.app.show_login()
