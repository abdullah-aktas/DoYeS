from __future__ import annotations

import flet as ft

from app.database import get_dashboard_summary, list_audit_logs, list_attendance_records, list_grade_records


class ReportsView(ft.Column):
    def __init__(self):
        self.summary = get_dashboard_summary()
        self.grid = ft.Row(wrap=True, spacing=12)
        self.audit_table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Aksiyon")),
            ft.DataColumn(ft.Text("Detay")),
            ft.DataColumn(ft.Text("Kullanıcı")),
        ], rows=[])
        self.attendance_table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Öğrenci")),
            ft.DataColumn(ft.Text("Tarih")),
            ft.DataColumn(ft.Text("Durum")),
            ft.DataColumn(ft.Text("Uyarı")),
        ], rows=[])
        self.grade_table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Öğrenci")),
            ft.DataColumn(ft.Text("Ders")),
            ft.DataColumn(ft.Text("Puan")),
            ft.DataColumn(ft.Text("Harf")),
        ], rows=[])
        super().__init__(
            spacing=18,
            controls=[
                ft.Text("Raporlar ve Grafikler", size=24, weight=ft.FontWeight.BOLD),
                self.grid,
                ft.Text("Son denetim kayıtları", weight=ft.FontWeight.BOLD),
                ft.Container(content=self.audit_table, border_radius=12, bgcolor="#ffffff", padding=10),
                ft.Text("Yoklama ve uyarı özeti", weight=ft.FontWeight.BOLD),
                ft.Container(content=self.attendance_table, border_radius=12, bgcolor="#ffffff", padding=10),
                ft.Text("Not durumu ve veli bildirimi", weight=ft.FontWeight.BOLD),
                ft.Container(content=self.grade_table, border_radius=12, bgcolor="#ffffff", padding=10),
            ],
        )
        self.refresh()

    def _stat_card(self, title: str, value: str, color: str):
        return ft.Container(
            content=ft.Column([
                ft.Text(title, size=13, color="#5a6474"),
                ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=color),
            ], alignment=ft.MainAxisAlignment.CENTER),
            width=220,
            height=120,
            padding=18,
            border_radius=14,
            bgcolor="#f5f8fb",
            border=ft.border.all(1, "#e2eaf5"),
        )

    def refresh(self):
        summary = get_dashboard_summary()
        self.grid.controls = [
            self._stat_card("Öğrenci sayısı", str(summary["student_count"]), "#1f4e78"),
            self._stat_card("Toplam belge", str(summary["approval_count"]), "#2e7d32"),
            self._stat_card("Bekleyen onay", str(summary["pending_approvals"]), "#f9a825"),
            self._stat_card("Uyarı atan öğrenci", str(summary["warning_attendance"]), "#d32f2f"),
        ]

        self.audit_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["action"])),
                ft.DataCell(ft.Text(item["details"])),
                ft.DataCell(ft.Text(item["actor"])),
            ]) for item in list_audit_logs()[:5]
        ]

        self.attendance_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["student_name"])),
                ft.DataCell(ft.Text(item["attendance_date"])),
                ft.DataCell(ft.Text(item["attendance_status"])),
                ft.DataCell(ft.Text(item["alert_level"])),
            ]) for item in list_attendance_records()[:5]
        ]

        self.grade_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["student_name"])),
                ft.DataCell(ft.Text(item["subject"])),
                ft.DataCell(ft.Text(item["score"])),
                ft.DataCell(ft.Text(item["letter_grade"])),
            ]) for item in list_grade_records()[:5]
        ]
