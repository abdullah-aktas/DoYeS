from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    username: str
    full_name: str
    role: str
    department: str = "Genel"
    active: bool = True
    last_login: Optional[datetime] = None


@dataclass
class PersonnelRecord:
    id: Optional[int] = None
    full_name: str = ""
    title: str = ""
    department: str = ""
    status: str = "Aktif"
    phone: str = ""
    email: str = ""


@dataclass
class OrderRecord:
    id: Optional[int] = None
    title: str = ""
    department: str = ""
    amount: float = 0.0
    creator: str = ""
    status: str = "Taslak"
    risk_level: str = "Normal"
    notes: str = ""
    created_at: Optional[datetime] = None


@dataclass
class ApprovalTask:
    task_id: str
    title: str
    creator: str
    current_stage: str
    status: str
    risk_level: str = "Normal"
    total_amount: float = 0.0
    due_date: Optional[str] = None
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AlertMessage:
    title: str
    detail: str
    severity: str = "info"
