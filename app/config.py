APP_NAME = "DÖSE Yönetim"
APP_VERSION = "0.2.0"
APP_COPYRIGHT = "© 2026 DÖSE"

ROLE_LABELS = {
    "admin": "Sistem Yöneticisi",
    "mudur": "Müdür",
    "mudur_yardimcisi": "Müdür Yardımcısı",
    "alan_sefi": "Alan Şefi",
    "ogretmen": "Öğretmen",
    "sayman": "Sayman",
    "memur": "Memur / Veri Girişi",
    "izleyici": "İzleyici / Denetçi",
}

FEATURES = {
    "dashboard": "Ana pano",
    "approvals": "Onay akışı",
    "personnel": "Personel",
    "orders": "Sipariş / İş emri",
    "students": "Öğrenci ve devamsızlık",
    "timesheet": "Fazla çalışma",
    "budget": "Bütçe ve muhasebe",
    "reports": "Raporlar",
    "mobile": "Mobil erişim",
    "security": "Güvenlik ve denetim",
}

ROLE_PERMISSIONS = {
    "admin": set(FEATURES.keys()),
    "mudur": {"dashboard", "personnel", "approvals", "orders", "students", "reports", "security"},
    "mudur_yardimcisi": {"dashboard", "personnel", "approvals", "orders", "students", "reports"},
    "alan_sefi": {"dashboard", "approvals", "orders", "students", "reports", "personnel"},
    "ogretmen": {"dashboard", "orders", "students", "reports", "timesheet"},
    "sayman": {"dashboard", "orders", "approvals", "budget", "reports"},
    "memur": {"dashboard", "orders", "students", "reports"},
    "izleyici": {"dashboard", "reports"},
}

APPROVAL_ROUTE = ("Alan Şefi", "Müdür Yardımcısı", "Sayman", "Müdür")
APPROVAL_STAGE_ROLES = {
    "Alan Şefi": "alan_sefi",
    "Müdür Yardımcısı": "mudur_yardimcisi",
    "Sayman": "sayman",
    "Müdür": "mudur",
}

APP_THEME = {
    "primary": "#1f4e78",
    "primary_light": "#dfeaf5",
    "success": "#2e7d32",
    "warning": "#f9a825",
    "danger": "#d32f2f",
    "neutral": "#5a6474",
}

DEVICE_THEMES = {
    "phone": {
        "bgcolor": "#f5f8fc",
        "card_bg": "#ffffff",
        "primary": "#1f4e78",
        "accent": "#5da5ff",
        "padding": 12,
    },
    "tablet": {
        "bgcolor": "#eef5ff",
        "card_bg": "#f9fbff",
        "primary": "#1f4e78",
        "accent": "#4b8df8",
        "padding": 16,
    },
    "desktop": {
        "bgcolor": "#f3f6fb",
        "card_bg": "#ffffff",
        "primary": "#1f4e78",
        "accent": "#2d6cdf",
        "padding": 20,
    },
}


def resolve_device_theme(width: int | float) -> str:
    if width < 480:
        return "phone"
    if width < 900:
        return "tablet"
    return "desktop"
