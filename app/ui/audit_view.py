from __future__ import annotations

import flet as ft

from app.database import list_audit_logs


class AuditView(ft.Column):
    def __init__(self):
        self.table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Aksiyon")),
            ft.DataColumn(ft.Text("Detay")),
            ft.DataColumn(ft.Text("Kullanıcı")),
            ft.DataColumn(ft.Text("Tarih")),
        ], rows=[])
        super().__init__(
            spacing=16,
            controls=[
                ft.Text("Denetim / Audit Takibi", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(content=self.table, padding=10, border_radius=12, bgcolor="#ffffff"),
            ],
        )
        self.refresh()

    def refresh(self):
        self.table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["action"])),
                ft.DataCell(ft.Text(item["details"])),
                ft.DataCell(ft.Text(item["actor"])),
                ft.DataCell(ft.Text(item["created_at"])),
            ]) for item in list_audit_logs()[:20]
        ]
