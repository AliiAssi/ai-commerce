from __future__ import annotations

from enum import StrEnum

from app.core.auth import ADMIN_ROLE, CUSTOMER_ROLE


class Permission(StrEnum):
    ADMIN_ACCESS = "admin:access"
    PRODUCTS_MANAGE = "products:manage"
    ORDERS_MANAGE = "orders:manage"
    AUDIT_VIEW = "audit:view"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    CUSTOMER_ROLE: frozenset(),
    ADMIN_ROLE: frozenset(Permission),
}


def has_permission(role: str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
