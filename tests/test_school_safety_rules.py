import unittest

from app.auth import calculate_risk_level, can_review_approval, get_role_permissions, validate_credentials
from app.config import resolve_device_theme
from app.database import (
    add_approval_log,
    add_attendance_record,
    add_audit_log,
    add_grade_record,
    add_parent_notification,
    add_student,
    get_dashboard_summary,
    initialize_schema,
    list_approval_logs,
    list_attendance_records,
    list_audit_logs,
    list_grade_records,
    list_parent_notifications,
    list_students,
    update_approval_status,
)


class SchoolSafetyRulesTests(unittest.TestCase):
    def setUp(self):
        initialize_schema()
        add_approval_log("Test belge", "Alan Şefi", "Bekliyor", "Dikkat", "admin")

    def test_calculate_risk_level(self):
        self.assertEqual(calculate_risk_level(150000, ""), "Kritik")
        self.assertEqual(calculate_risk_level(25000, "Yüksek riskli işlem"), "Yüksek")
        self.assertEqual(calculate_risk_level(12000, "Standart işlem"), "Normal")

    def test_role_permissions(self):
        teacher_permissions = get_role_permissions("ogretmen")
        accountant_permissions = get_role_permissions("sayman")
        self.assertIn("dashboard", teacher_permissions)
        self.assertIn("reports", teacher_permissions)
        self.assertIn("approvals", accountant_permissions)
        self.assertNotIn("personnel", teacher_permissions)
        self.assertNotIn("approvals", teacher_permissions)

    def test_approval_authority_is_stage_limited_and_blocks_self_approval(self):
        self.assertTrue(can_review_approval("alan_sefi", "chief", "teacher", "Alan Şefi"))
        self.assertFalse(can_review_approval("ogretmen", "teacher", "teacher", "Alan Şefi"))
        self.assertFalse(can_review_approval("admin", "admin", "teacher", "Alan Şefi"))
        self.assertFalse(can_review_approval("mudur", "principal", "principal", "Müdür"))
        self.assertFalse(can_review_approval("sayman", "accountant", "teacher", "Müdür"))

    def test_validate_credentials_for_admin(self):
        ok, result = validate_credentials("admin", "admin")
        self.assertTrue(ok)
        self.assertEqual(result["role"], "admin")

    def test_update_approval_status(self):
        self.assertFalse(update_approval_status("Test belge", "Onaylandı", "mudur"))
        row = next(item for item in list_approval_logs() if item["task_title"] == "Test belge")
        self.assertEqual(row["status"], "Bekliyor")
        self.assertEqual(row["current_stage"], "Alan Şefi")

        for username, next_stage in [
            ("alan_sefi", "Müdür Yardımcısı"),
            ("mudur_yardimcisi", "Sayman"),
            ("sayman", "Müdür"),
        ]:
            self.assertTrue(update_approval_status("Test belge", "Onaylandı", username))
            row = next(item for item in list_approval_logs() if item["task_title"] == "Test belge")
            self.assertEqual(row["status"], "Bekliyor")
            self.assertEqual(row["current_stage"], next_stage)

        self.assertTrue(update_approval_status("Test belge", "Onaylandı", "mudur"))
        row = next(item for item in list_approval_logs() if item["task_title"] == "Test belge")
        self.assertEqual(row["status"], "Onaylandı")
        self.assertEqual(row["current_stage"], "Müdür")

    def test_student_and_attendance_tracking(self):
        add_student("Ali Veli", "12-A", "Matematik", "İzleme")
        add_attendance_record("Ali Veli", "2026-10-13", "Geç geldi", "Uyarı")
        students = list_students()
        attendance = list_attendance_records()
        self.assertTrue(any(student["student_name"] == "Ali Veli" for student in students))
        self.assertTrue(any(record["student_name"] == "Ali Veli" for record in attendance))

    def test_reporting_and_audit_and_grade_flow(self):
        add_student("Ayşe Demir", "10-B", "Türkçe", "Normal")
        add_grade_record("Ayşe Demir", "Türkçe", "90", "A", "Veli bilgilendirme gönderildi")
        add_audit_log("grade_entry", "Ayşe Demir için not eklendi", "admin")
        summary = get_dashboard_summary()
        self.assertGreater(summary["student_count"], 0)
        self.assertGreater(summary["approval_count"], 0)
        self.assertTrue(any(record["student_name"] == "Ayşe Demir" for record in list_grade_records()))
        self.assertTrue(any(entry["action"] == "grade_entry" for entry in list_audit_logs()))

    def test_parent_email_and_sms_notifications_and_device_theme(self):
        add_parent_notification(
            "Ayşe Demir",
            "email",
            "veli@okul.com",
            "Not bildirimi: Türkçe dersi için 90 puan",
            "Gönderildi",
        )
        add_parent_notification(
            "Ayşe Demir",
            "sms",
            "+905551112233",
            "Not bildirimi: Türkçe dersi için 90 puan",
            "Gönderildi",
        )
        notifications = list_parent_notifications()
        self.assertTrue(any(item["student_name"] == "Ayşe Demir" and item["channel"] == "email" for item in notifications))
        self.assertTrue(any(item["student_name"] == "Ayşe Demir" and item["channel"] == "sms" for item in notifications))
        self.assertEqual(resolve_device_theme(600), "tablet")
        self.assertEqual(resolve_device_theme(390), "phone")


if __name__ == "__main__":
    unittest.main()
