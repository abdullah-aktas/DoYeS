from __future__ import annotations

import flet as ft

from app.database import (
    add_audit_log,
    add_attendance_record,
    add_grade_record,
    add_leave_request,
    add_student,
    list_attendance_records,
    list_grade_records,
    list_leave_requests,
    list_students,
)
from app.notifications import deliver_parent_notifications


class StudentView(ft.Column):
    def __init__(self):
        self.student_name = ft.TextField(label="Öğrenci adı")
        self.class_name = ft.TextField(label="Sınıf / Şube")
        self.department = ft.Dropdown(
            label="Bölüm",
            options=[
                ft.dropdown.Option("Matematik"),
                ft.dropdown.Option("Fen Bilimleri"),
                ft.dropdown.Option("Türkçe"),
                ft.dropdown.Option("Sosyal"),
                ft.dropdown.Option("Genel"),
            ],
        )
        self.status = ft.Dropdown(
            label="Durum",
            options=[
                ft.dropdown.Option("Normal"),
                ft.dropdown.Option("İzleme"),
                ft.dropdown.Option("Dikkat"),
            ],
            value="Normal",
        )
        self.attendance_date = ft.TextField(label="Tarih (YYYY-AA-GG)")
        self.attendance_status = ft.Dropdown(
            label="Devamsızlık / Yoklama",
            options=[
                ft.dropdown.Option("Geldi"),
                ft.dropdown.Option("Geç geldi"),
                ft.dropdown.Option("Devamsız"),
                ft.dropdown.Option("İzinli"),
            ],
            value="Geldi",
        )
        self.alert_level = ft.Dropdown(
            label="Uyarı seviyesi",
            options=[
                ft.dropdown.Option("Normal"),
                ft.dropdown.Option("Uyarı"),
                ft.dropdown.Option("Önemli"),
            ],
            value="Normal",
        )
        self.leave_date = ft.TextField(label="İzin tarihi")
        self.leave_reason = ft.TextField(label="İzin nedeni", multiline=True, min_lines=2)
        self.grade_subject = ft.TextField(label="Ders")
        self.grade_score = ft.TextField(label="Puan")
        self.grade_letter = ft.TextField(label="Harf notu")
        self.parent_email = ft.TextField(label="Veli e-posta")
        self.parent_phone = ft.TextField(label="Veli SMS")
        self.notification_channel = ft.Dropdown(
            label="Bildirim yolu",
            options=[
                ft.dropdown.Option("email"),
                ft.dropdown.Option("sms"),
                ft.dropdown.Option("both"),
            ],
            value="email",
        )
        self.grade_notification = ft.TextField(label="Veli bilgilendirme metni", multiline=True, min_lines=2)
        self.message = ft.Text(value="", color="green")

        self.student_table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Öğrenci")),
            ft.DataColumn(ft.Text("Sınıf")),
            ft.DataColumn(ft.Text("Bölüm")),
            ft.DataColumn(ft.Text("Durum")),
        ], rows=[])
        self.attendance_table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Öğrenci")),
            ft.DataColumn(ft.Text("Tarih")),
            ft.DataColumn(ft.Text("Durum")),
            ft.DataColumn(ft.Text("Uyarı")),
        ], rows=[])
        self.leave_table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("Öğrenci")),
            ft.DataColumn(ft.Text("Tarih")),
            ft.DataColumn(ft.Text("Neden")),
            ft.DataColumn(ft.Text("Durum")),
        ], rows=[])

        super().__init__(
            spacing=16,
            controls=[
                ft.Text("Öğrenci ve Devamsızlık Takibi", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Öğrenci kaydı", weight=ft.FontWeight.BOLD),
                        ft.Row([self.student_name, self.class_name, self.department], wrap=True),
                        ft.Row([self.status, ft.ElevatedButton("Öğrenci ekle", on_click=self.save_student)], wrap=True),
                    ]),
                    padding=12,
                    border_radius=12,
                    bgcolor="#f8fbff",
                    border=ft.border.all(1, "#dfeaf5"),
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Yoklama / devamsızlık", weight=ft.FontWeight.BOLD),
                        ft.Row([self.attendance_date, self.attendance_status, self.alert_level], wrap=True),
                        ft.ElevatedButton("Yoklama kaydet", on_click=self.save_attendance),
                    ]),
                    padding=12,
                    border_radius=12,
                    bgcolor="#fffdf6",
                    border=ft.border.all(1, "#f2e0a3"),
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("İzin talebi", weight=ft.FontWeight.BOLD),
                        ft.Row([self.leave_date, self.leave_reason], wrap=True),
                        ft.ElevatedButton("İzin kaydet", on_click=self.save_leave),
                    ]),
                    padding=12,
                    border_radius=12,
                    bgcolor="#f4fbf5",
                    border=ft.border.all(1, "#cceddc"),
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Not ve veli bilgilendirme", weight=ft.FontWeight.BOLD),
                        ft.Row([self.grade_subject, self.grade_score, self.grade_letter], wrap=True),
                        ft.Row([self.parent_email, self.parent_phone, self.notification_channel], wrap=True),
                        self.grade_notification,
                        ft.ElevatedButton("Not kaydet ve veliye bildir", on_click=self.save_grade),
                    ]),
                    padding=12,
                    border_radius=12,
                    bgcolor="#f7f2ff",
                    border=ft.border.all(1, "#e0d5ff"),
                ),
                self.message,
                ft.Text("Öğrenci listesi", weight=ft.FontWeight.BOLD),
                ft.Container(content=self.student_table, padding=10, border_radius=12, bgcolor="#ffffff"),
                ft.Text("Yoklama listesi", weight=ft.FontWeight.BOLD),
                ft.Container(content=self.attendance_table, padding=10, border_radius=12, bgcolor="#ffffff"),
                ft.Text("İzin talepleri", weight=ft.FontWeight.BOLD),
                ft.Container(content=self.leave_table, padding=10, border_radius=12, bgcolor="#ffffff"),
                ft.Text("Not takibi ve veli bildirimi", weight=ft.FontWeight.BOLD),
                ft.Container(content=ft.DataTable(columns=[
                    ft.DataColumn(ft.Text("Öğrenci")),
                    ft.DataColumn(ft.Text("Ders")),
                    ft.DataColumn(ft.Text("Puan")),
                    ft.DataColumn(ft.Text("Harf")),
                    ft.DataColumn(ft.Text("Veli notu")),
                ], rows=[]), padding=10, border_radius=12, bgcolor="#ffffff"),
            ],
        )
        self.grade_table = self.controls[-1].content
        self.refresh_tables()

    def save_student(self, e):
        name = self.student_name.value.strip()
        class_name = self.class_name.value.strip()
        department = self.department.value or "Genel"
        status = self.status.value or "Normal"
        if not name or not class_name:
            self.message.value = "Öğrenci adı ve sınıf alanı zorunludur."
            self.message.color = "red"
            self.update()
            return

        add_student(name, class_name, department, status)
        add_audit_log("student_create", f"{name} öğrencisi eklendi", "admin")
        self.message.value = "Öğrenci kaydı eklendi."
        self.message.color = "green"
        self.student_name.value = ""
        self.class_name.value = ""
        self.department.value = None
        self.status.value = "Normal"
        self.refresh_tables()
        self.update()

    def save_attendance(self, e):
        name = self.student_name.value.strip() or "Belirtilmemiş öğrenci"
        date_value = self.attendance_date.value.strip() or "2026-10-13"
        state = self.attendance_status.value or "Geldi"
        level = self.alert_level.value or "Normal"
        add_attendance_record(name, date_value, state, level)
        add_audit_log("attendance_record", f"{name} için {state} kaydı eklendi", "admin")
        self.message.value = "Yoklama kaydı eklendi."
        self.message.color = "green"
        self.refresh_tables()
        self.update()

    def save_leave(self, e):
        name = self.student_name.value.strip() or "Belirtilmemiş öğrenci"
        leave_date = self.leave_date.value.strip() or "2026-10-13"
        reason = self.leave_reason.value.strip()
        if not reason:
            self.message.value = "İzin nedeni zorunludur."
            self.message.color = "red"
            self.update()
            return
        add_leave_request(name, leave_date, reason)
        add_audit_log("leave_request", f"{name} için izin talebi kaydedildi", "admin")
        self.message.value = "İzin talebi kaydedildi."
        self.message.color = "green"
        self.leave_date.value = ""
        self.leave_reason.value = ""
        self.refresh_tables()
        self.update()

    def save_grade(self, e):
        name = self.student_name.value.strip() or "Belirtilmemiş öğrenci"
        subject = self.grade_subject.value.strip()
        score = self.grade_score.value.strip()
        letter = self.grade_letter.value.strip() or "-"
        notification = self.grade_notification.value.strip() or "Veli bilgilendirme gönderildi"
        channel = self.notification_channel.value or "email"
        email = self.parent_email.value.strip() or f"{name.lower().replace(' ', '')}@veli.local"
        phone = self.parent_phone.value.strip() or "+905550000000"
        if not subject or not score:
            self.message.value = "Ders ve puan zorunludur."
            self.message.color = "red"
            self.update()
            return
        add_grade_record(name, subject, score, letter, notification)
        body = f"{subject}: {score} puan ({letter}) - {notification}"
        deliver_parent_notifications(
            name,
            channel=channel,
            email=email,
            phone=phone,
            subject=f"{subject} not bildirimi",
            message=body,
        )
        add_audit_log("grade_entry", f"{name} için {subject} notu kaydedildi", "admin")
        self.message.value = "Not kaydedildi ve veli bilgilendirmesi hazırlandı."
        self.message.color = "green"
        self.grade_subject.value = ""
        self.grade_score.value = ""
        self.grade_letter.value = ""
        self.parent_email.value = ""
        self.parent_phone.value = ""
        self.notification_channel.value = "email"
        self.grade_notification.value = ""
        self.refresh_tables()
        self.update()

    def refresh_tables(self):
        students = list_students()
        self.student_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["student_name"])),
                ft.DataCell(ft.Text(item["class_name"])),
                ft.DataCell(ft.Text(item["department"])),
                ft.DataCell(ft.Text(item["status"])),
            ]) for item in students
        ]

        attendance = list_attendance_records()
        self.attendance_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["student_name"])),
                ft.DataCell(ft.Text(item["attendance_date"])),
                ft.DataCell(ft.Text(item["attendance_status"])),
                ft.DataCell(ft.Text(item["alert_level"])),
            ]) for item in attendance
        ]

        leave_requests = list_leave_requests()
        self.leave_table.rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["student_name"])),
                ft.DataCell(ft.Text(item["leave_date"])),
                ft.DataCell(ft.Text(item["reason"])),
                ft.DataCell(ft.Text(item["status"])),
            ]) for item in leave_requests
        ]

        grade_list = list_grade_records()
        if hasattr(self, "grade_table"):
            self.grade_table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(item["student_name"])),
                    ft.DataCell(ft.Text(item["subject"])),
                    ft.DataCell(ft.Text(item["score"])),
                    ft.DataCell(ft.Text(item["letter_grade"])),
                    ft.DataCell(ft.Text(item["notification_text"])),
                ]) for item in grade_list
            ]
