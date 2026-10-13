from __future__ import annotations

import flet as ft

from app.auth import calculate_risk_level
from app.database import add_approval_log, add_audit_log, save_order


class OrderView(ft.Column):
    def __init__(self, username: str = "admin"):
        self.username = username
        self.title = ft.TextField(label="İş emri / sipariş başlığı")
        self.department = ft.Dropdown(
            label="Bölüm",
            options=[
                ft.dropdown.Option("Fen Bilimleri"),
                ft.dropdown.Option("Matematik"),
                ft.dropdown.Option("Yönetim"),
            ],
        )
        self.amount = ft.TextField(label="Tahmini tutar (₺)", keyboard_type=ft.KeyboardType.NUMBER)
        self.document_reference = ft.TextField(label="Dayanak belge / talep no")
        self.notes = ft.TextField(label="Açıklama", multiline=True, min_lines=4)
        self.need_confirmed = ft.Checkbox(label="İhtiyaç ve miktar gerekçesini kontrol ettim")
        self.budget_confirmed = ft.Checkbox(label="Ödenek / bütçe durumunu yetkiliyle teyit ettim")
        self.procedure_confirmed = ft.Checkbox(label="Okulun güncel satın alma usulünü kontrol ettim")
        self.authority_confirmed = ft.Checkbox(label="Yetki ve onay sırasını kontrol ettim")
        self.message = ft.Text(value="", color="green")

        super().__init__(
            spacing=18,
            controls=[
                ft.Text("Sipariş / İş Emri", size=24, weight=ft.FontWeight.BOLD),
                ft.Row([
                    self.title,
                    self.department,
                    self.amount,
                ], wrap=True),
                self.document_reference,
                self.notes,
                ft.Container(
                    content=ft.Column([
                        ft.Text("Göndermeden önce kontrol edin", weight=ft.FontWeight.BOLD),
                        ft.Text("Bu kontrol listesi hatırlatmadır; güncel mevzuat, kurum talimatı ve yetki devrinin yerine geçmez."),
                        self.need_confirmed,
                        self.budget_confirmed,
                        self.procedure_confirmed,
                        self.authority_confirmed,
                    ], spacing=8),
                    padding=12,
                    bgcolor="#fff8df",
                    border=ft.border.all(1, "#e7cf78"),
                    border_radius=8,
                ),
                ft.Row([
                    ft.ElevatedButton("Kaydet ve gönder", icon=ft.Icons.SEND_ROUNDED, on_click=self.save_order),
                    ft.OutlinedButton("Taslak olarak kaydet", icon=ft.Icons.SAVE_ROUNDED),
                ], wrap=True),
                self.message,
            ],
        )

    def save_order(self, e):
        title = self.title.value.strip()
        department = self.department.value or "Genel"
        amount_text = self.amount.value.strip()
        document_reference = self.document_reference.value.strip()
        notes = self.notes.value.strip()

        if not title or not amount_text:
            self.message.value = "Sipariş başlığı ve tutar zorunludur."
            self.message.color = "red"
            self.update()
            return

        checks = [
            self.need_confirmed.value,
            self.budget_confirmed.value,
            self.procedure_confirmed.value,
            self.authority_confirmed.value,
        ]
        if not document_reference or not all(checks):
            self.message.value = "Dayanak belge/talep numarası ve tüm ön kontroller zorunludur."
            self.message.color = "red"
            self.update()
            return

        try:
            amount = float(amount_text)
        except ValueError:
            self.message.value = "Tutar sayısal olmalıdır."
            self.message.color = "red"
            self.update()
            return

        risk_level = calculate_risk_level(amount, notes)
        order_notes = f"Dayanak belge/talep no: {document_reference}\n{notes}".strip()
        save_order(title, department, amount, self.username, order_notes)
        add_approval_log(title, "Alan Şefi", "Bekliyor", risk_level, self.username)
        add_audit_log("order_submit", f"{title} gönderildi; dayanak {document_reference}; risk sınıfı {risk_level}", self.username)
        self.message.value = "Sipariş kaydedildi ve onay akışına alındı."
        self.message.color = "green"
        self.title.value = ""
        self.department.value = None
        self.amount.value = ""
        self.document_reference.value = ""
        self.notes.value = ""
        self.need_confirmed.value = False
        self.budget_confirmed.value = False
        self.procedure_confirmed.value = False
        self.authority_confirmed.value = False
        self.update()
