from __future__ import annotations

from app.config import APPROVAL_STAGE_ROLES, ROLE_PERMISSIONS
from app.database import get_user


def calculate_risk_level(amount: float, notes: str = "") -> str:
    text = (notes or "").lower()
    if amount >= 100000 or "kural dışı" in text or "ceza" in text or "kritik" in text:
        return "Kritik"
    if amount >= 25000 or "yüksek" in text or "acil" in text or "riskli" in text:
        return "Yüksek"
    if "dikkat" in text:
        return "Dikkat"
    return "Normal"


def get_role_permissions(role: str):
    if not role:
        return set()
    return set(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS.get("izleyici", set())))


def can_review_approval(role: str, username: str, creator: str, stage: str) -> bool:
    if not username or username == creator:
        return False
    return role == APPROVAL_STAGE_ROLES.get(stage)


def user_has_access(username: str, feature: str) -> bool:
    user = get_user(username)
    if not user:
        return False
    return feature in get_role_permissions(user.get("role"))


def validate_credentials(username: str, password: str):
    if not username or not password:
        return False, "Kullanıcı adı ve şifre zorunludur."

    user = get_user(username)
    if not user:
        return False, "Bu kullanıcı bulunamadı."

    if user.get("active") in (0, False):
        return False, "Bu kullanıcı pasif durumda; yöneticinizle iletişime geçin."

    stored_password = user.get("password") or "admin"
    if password != stored_password:
        return False, "Şifre yanlış."

    return True, user
