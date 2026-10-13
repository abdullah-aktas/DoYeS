from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from app.config import APPROVAL_ROUTE, APPROVAL_STAGE_ROLES

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "dose.db"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_schema() -> None:
    conn = connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                password TEXT NOT NULL DEFAULT 'admin'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personnel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                title TEXT NOT NULL,
                department TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Aktif',
                phone TEXT,
                email TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                department TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                creator TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Taslak',
                risk_level TEXT NOT NULL DEFAULT 'Normal',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approval_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_title TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                performer TEXT NOT NULL,
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        approval_columns = {row["name"] for row in conn.execute("PRAGMA table_info(approval_logs)").fetchall()}
        if "created_by" not in approval_columns:
            conn.execute("ALTER TABLE approval_logs ADD COLUMN created_by TEXT NOT NULL DEFAULT ''")
            conn.execute("UPDATE approval_logs SET created_by = performer WHERE created_by = ''")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                class_name TEXT NOT NULL,
                department TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Normal',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                attendance_status TEXT NOT NULL,
                alert_level TEXT NOT NULL DEFAULT 'Normal',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Bekliyor',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS grade_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                subject TEXT NOT NULL,
                score TEXT NOT NULL,
                letter_grade TEXT NOT NULL,
                notification_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parent_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                channel TEXT NOT NULL,
                recipient TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Gönderildi',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        default_users = [
            ("admin", "Yönetici", "admin", "Genel", "admin"),
            ("mudur", "Müdür", "mudur", "Yönetim", "admin"),
            ("mudur_yardimcisi", "Müdür Yardımcısı", "mudur_yardimcisi", "Yönetim", "admin"),
            ("alan_sefi", "Alan Şefi", "alan_sefi", "Fen Bilimleri", "admin"),
            ("ogretmen", "Öğretmen", "ogretmen", "Matematik", "admin"),
            ("sayman", "Sayman", "sayman", "Muhasebe", "admin"),
            ("memur", "Memur", "memur", "Genel", "admin"),
        ]
        for username, full_name, role, department, password in default_users:
            conn.execute(
                "INSERT OR IGNORE INTO users (username, full_name, role, department, password) VALUES (?, ?, ?, ?, ?)",
                (username, full_name, role, department, password),
            )
        conn.commit()
    finally:
        conn.close()


def get_user(username: str):
    initialize_schema()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT username, full_name, role, department, active, password FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_personnel(full_name: str, title: str, department: str, status: str = "Aktif", phone: str = "", email: str = "") -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO personnel (full_name, title, department, status, phone, email) VALUES (?, ?, ?, ?, ?, ?)",
            (full_name, title, department, status, phone, email),
        )
        conn.commit()
    finally:
        conn.close()


def list_personnel() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, full_name, title, department, status, phone, email FROM personnel ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_order(title: str, department: str, amount: float, creator: str, notes: str = "") -> None:
    risk_level = "Riskli" if amount >= 50000 else "Dikkat" if amount >= 20000 else "Normal"
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO orders (title, department, amount, creator, status, risk_level, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, department, amount, creator, "Bekliyor", risk_level, notes),
        )
        conn.commit()
    finally:
        conn.close()


def list_orders() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, title, department, amount, creator, status, risk_level, notes, created_at FROM orders ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_approval_log(task_title: str, current_stage: str, status: str, risk_level: str, performer: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO approval_logs (task_title, current_stage, status, risk_level, performer, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (task_title, current_stage, status, risk_level, performer, performer),
        )
        conn.commit()
    finally:
        conn.close()


def update_approval_status(task_title: str, new_status: str, performer: str, stage_name: str | None = None) -> bool:
    conn = connect()
    try:
        if new_status not in {"Onaylandı", "İade edildi"}:
            return False
        row = conn.execute(
            "SELECT id, current_stage, created_by FROM approval_logs WHERE task_title = ? AND status = 'Bekliyor' ORDER BY id DESC LIMIT 1",
            (task_title,),
        ).fetchone()
        if row is None:
            return False
        user = conn.execute(
            "SELECT role, active FROM users WHERE username = ?",
            (performer,),
        ).fetchone()
        expected_role = APPROVAL_STAGE_ROLES.get(row["current_stage"])
        if (
            user is None
            or not user["active"]
            or performer == row["created_by"]
            or user["role"] != expected_role
        ):
            return False

        if new_status == "Onaylandı":
            route_index = APPROVAL_ROUTE.index(row["current_stage"])
            is_final_stage = route_index == len(APPROVAL_ROUTE) - 1
            current_stage = row["current_stage"] if is_final_stage else APPROVAL_ROUTE[route_index + 1]
            status = "Onaylandı" if is_final_stage else "Bekliyor"
        else:
            current_stage = row["current_stage"]
            status = "İade edildi"
        conn.execute(
            "UPDATE approval_logs SET status = ?, current_stage = ?, performer = ? WHERE id = ?",
            (status, current_stage, performer, row["id"]),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def list_approval_logs() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, task_title, current_stage, status, risk_level, performer, created_by, created_at FROM approval_logs ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_pending_approvals() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, task_title, current_stage, status, risk_level, performer, created_by, created_at FROM approval_logs WHERE status = 'Bekliyor' ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_dashboard_summary() -> Dict[str, Any]:
    conn = connect()
    try:
        student_count = conn.execute("SELECT COUNT(*) AS total FROM students").fetchone()["total"]
        approval_count = conn.execute("SELECT COUNT(*) AS total FROM approval_logs").fetchone()["total"]
        pending_approvals = conn.execute("SELECT COUNT(*) AS total FROM approval_logs WHERE status = 'Bekliyor'").fetchone()["total"]
        warning_attendance = conn.execute("SELECT COUNT(*) AS total FROM attendance_records WHERE alert_level IN ('Uyarı', 'Önemli')").fetchone()["total"]
        grade_count = conn.execute("SELECT COUNT(*) AS total FROM grade_records").fetchone()["total"]
        return {
            "student_count": student_count,
            "approval_count": approval_count,
            "pending_approvals": pending_approvals,
            "warning_attendance": warning_attendance,
            "grade_count": grade_count,
        }
    finally:
        conn.close()


def add_student(student_name: str, class_name: str, department: str, status: str = "Normal") -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO students (student_name, class_name, department, status) VALUES (?, ?, ?, ?)",
            (student_name, class_name, department, status),
        )
        conn.commit()
    finally:
        conn.close()


def list_students() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, student_name, class_name, department, status, created_at FROM students ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_attendance_record(student_name: str, attendance_date: str, attendance_status: str, alert_level: str = "Normal") -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO attendance_records (student_name, attendance_date, attendance_status, alert_level) VALUES (?, ?, ?, ?)",
            (student_name, attendance_date, attendance_status, alert_level),
        )
        conn.commit()
    finally:
        conn.close()


def list_attendance_records() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, student_name, attendance_date, attendance_status, alert_level, created_at FROM attendance_records ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_leave_request(student_name: str, leave_date: str, reason: str, status: str = "Bekliyor") -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO leave_requests (student_name, leave_date, reason, status) VALUES (?, ?, ?, ?)",
            (student_name, leave_date, reason, status),
        )
        conn.commit()
    finally:
        conn.close()


def list_leave_requests() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, student_name, leave_date, reason, status, created_at FROM leave_requests ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_audit_log(action: str, details: str, actor: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO audit_logs (action, details, actor) VALUES (?, ?, ?)",
            (action, details, actor),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit_logs() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, action, details, actor, created_at FROM audit_logs ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_grade_record(student_name: str, subject: str, score: str, letter_grade: str, notification_text: str = "") -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO grade_records (student_name, subject, score, letter_grade, notification_text) VALUES (?, ?, ?, ?, ?)",
            (student_name, subject, score, letter_grade, notification_text),
        )
        conn.commit()
    finally:
        conn.close()


def list_grade_records() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, student_name, subject, score, letter_grade, notification_text, created_at FROM grade_records ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_parent_notification(student_name: str, channel: str, recipient: str, message: str, status: str = "Gönderildi") -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO parent_notifications (student_name, channel, recipient, message, status) VALUES (?, ?, ?, ?, ?)",
            (student_name, channel, recipient, message, status),
        )
        conn.commit()
    finally:
        conn.close()


def list_parent_notifications() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, student_name, channel, recipient, message, status, created_at FROM parent_notifications ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
