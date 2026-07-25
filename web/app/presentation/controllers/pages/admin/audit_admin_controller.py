from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.application.iservices.iadmin_service import IAdminService
from app.core.auth import AuthenticatedUser
from app.core.authz import Permission
from app.core.container import Injected
from app.presentation.guards import require_permission
from app.presentation.templates import render

router = APIRouter(prefix="/admin/audit")

_view = require_permission(Permission.AUDIT_VIEW)
_PAGE_SIZE = 20


@router.get("")
async def audit_list(
    request: Request,
    page: int = 1,
    admin: AuthenticatedUser = Depends(_view),
    admin_service: IAdminService = Injected(IAdminService),
):
    result = await admin_service.audit_page(max(page, 1), _PAGE_SIZE)
    return render(
        request,
        "admin/audit.html",
        {
            "entries": result.items,
            "page": result.page,
            "pages": (result.total + _PAGE_SIZE - 1) // _PAGE_SIZE,
            "qs": "",
            "active_nav": "audit",
        },
        user=admin,
    )
