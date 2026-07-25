from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.application.iservices.iadmin_service import IAdminService
from app.core.auth import AuthenticatedUser
from app.core.authz import Permission
from app.core.container import Injected
from app.presentation.guards import require_permission
from app.presentation.templates import render

router = APIRouter(prefix="/admin")

_admin_access = require_permission(Permission.ADMIN_ACCESS)


@router.get("")
async def dashboard(
    request: Request,
    admin: AuthenticatedUser = Depends(_admin_access),
    admin_service: IAdminService = Injected(IAdminService),
):
    stats = await admin_service.dashboard()
    return render(
        request,
        "admin/dashboard.html",
        {"stats": stats, "active_nav": "dashboard"},
        user=admin,
    )
