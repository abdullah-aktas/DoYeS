from __future__ import annotations

import flet as ft

from app.auth import can_review_approval
from app.database import add_audit_log, list_approval_logs, update_approval_status


class ApprovalsView(ft.Column):
    def __init__(self, username: str, role: str):
        self.username = username
        self.role = role
        self.table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Belge")),
            ft.DataColumn(ft.Text("Aşama")),
            ft.DataColumn(ft.Text("Durum")),
            ft.DataColumn(ft.Text("Risk")),
            ft.DataColumn(ft.Text("İşleyen")),
            ft.DataColumn(ft.Text("İşlem")),
        ], rows=[])
        super().__init__(
            spacing=16,
            controls=[
                ft.Text("Onay Bekleyenler", size=24, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.OutlinedButton("Geçmiş", icon=ft.Icons.HISTORY_ROUNDED, on_click=self.show_history),
                ], wrap=True),
                ft.Container(
                    content=self.table,
                    border_radius=12,
                    padding=10,
                    bgcolor="#ffffff",
                ),
            ],
        )
        self.refresh_table()

    def show_history(self, e):
        self.refresh_table(show_all=True)

    def refresh_table(self, show_all: bool = False):
        rows = []
        items = list_approval_logs() if show_all else [item for item in list_approval_logs() if item["status"] == "Bekliyor"]
        for item in items:
            can_review = can_review_approval(self.role, self.username, item["created_by"], item["current_stage"])
            action_row = ft.Row(
                controls=[
                    ft.IconButton(ft.Icons.CHECK_ROUNDED, tooltip="İncelemeyi tamamla", on_click=lambda e, row=item: self.handle_decision(row, "Onaylandı")),
                    ft.IconButton(ft.Icons.CLOSE_ROUNDED, tooltip="İade et", on_click=lambda e, row=item: self.handle_decision(row, "İade edildi")),
                ] if can_review and item["status"] == "Bekliyor" else [ft.Text("Yetki yok / işlem kapalı")],
            )
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["task_title"])),
                ft.DataCell(ft.Text(item["current_stage"])),
                ft.DataCell(ft.Text(item["status"])),
                ft.DataCell(ft.Text(item["risk_level"])),
                ft.DataCell(ft.Text(item["performer"])),
                ft.DataCell(action_row),
            ]))
        self.table.rows = rows

    def handle_decision(self, item, status):
        if not can_review_approval(self.role, self.username, item["created_by"], item["current_stage"]):
            return
        if not update_approval_status(item["task_title"], status, self.username, item["current_stage"]):
            self.refresh_table()
            return
        add_audit_log("approval_decision", f"{item['task_title']}: {status} ({item['current_stage']})", self.username)
        self.refresh_table()
