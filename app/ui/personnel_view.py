from __future__ import annotations

import flet as ft

from app.database import list_personnel, save_personnel


class PersonnelView(ft.Column):
    def __init__(self):
        self.full_name = ft.TextField(label="Ad Soyad")
        self.title = ft.TextField(label="Unvan")
        self.department = ft.Dropdown(
            label="Bölüm",
            options=[
                ft.dropdown.Option("Yönetim"),
                ft.dropdown.Option("Fen Bilimleri"),
                ft.dropdown.Option("Matematik"),
                ft.dropdown.Option("Sosyal Bilgiler"),
                ft.dropdown.Option("Genel"),
            ],
        )
        self.phone = ft.TextField(label="Telefon")
        self.email = ft.TextField(label="E-posta")
        self.status = ft.Dropdown(
            label="Durum",
            options=[
                ft.dropdown.Option("Aktif"),
                ft.dropdown.Option("Pasif"),
            ],
            value="Aktif",
        )
        self.message = ft.Text(value="", color="green")
        self.table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Ad Soyad")),
            ft.DataColumn(ft.Text("Unvan")),
            ft.DataColumn(ft.Text("Bölüm")),
            ft.DataColumn(ft.Text("Durum")),
        ], rows=[])
        super().__init__(
            spacing=16,
            controls=[
                ft.Text("Personel Yönetimi", size=24, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.ElevatedButton("Yeni personel", icon=ft.Icons.PERSON_ADD_ROUNDED, on_click=self.save_personnel),
                    ft.OutlinedButton("İçe aktar", icon=ft.Icons.UPLOAD_FILE_ROUNDED),
                    ft.OutlinedButton("Excel", icon=ft.Icons.TABLE_ROWS_ROUNDED),
                ], wrap=True),
                ft.Container(
                    content=ft.Column([
                        ft.Row([self.full_name, self.title], wrap=True),
                        ft.Row([self.department, self.phone, self.email], wrap=True),
                        ft.Row([self.status, self.message], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ]),
                    padding=12,
                    border_radius=12,
                    bgcolor="#f8fbff",
                    border=ft.border.all(1, "#dfeaf5"),
                ),
                ft.Container(
                    content=self.table,
                    border_radius=12,
                    padding=10,
                    bgcolor="#ffffff",
                ),
            ],
        )
        self.refresh_table()

    def save_personnel(self, e):
        full_name = self.full_name.value.strip()
        title = self.title.value.strip()
        department = self.department.value.strip() if self.department.value else "Genel"
        status = self.status.value or "Aktif"
        phone = self.phone.value.strip()
        email = self.email.value.strip()

        if not full_name or not title:
            self.message.value = "Ad soyad ve unvan zorunludur."
            self.message.color = "red"
            self.update()
            return

        save_personnel(full_name, title, department, status, phone, email)
        self.message.value = "Personel kaydı eklendi."
        self.message.color = "green"
        self.full_name.value = ""
        self.title.value = ""
        self.department.value = None
        self.phone.value = ""
        self.email.value = ""
        self.status.value = "Aktif"
        self.refresh_table()
        self.update()

    def refresh_table(self):
        items = list_personnel()
        rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["full_name"])),
                ft.DataCell(ft.Text(item["title"])),
                ft.DataCell(ft.Text(item["department"])),
                ft.DataCell(ft.Text(item["status"])),
            ]) for item in items
        ]
        self.table.rows = rows
        if self.table.rows:
            self.table.columns = [
                ft.DataColumn(ft.Text("Ad Soyad")),
                ft.DataColumn(ft.Text("Unvan")),
                ft.DataColumn(ft.Text("Bölüm")),
                ft.DataColumn(ft.Text("Durum")),
            ]

