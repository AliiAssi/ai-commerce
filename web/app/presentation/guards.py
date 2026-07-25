from __future__ import annotations

from fastapi import Depends

from app.application.iservices.iauth_service import IAuthService
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.authz import Permission, has_permission
from app.core.container import Scope, get_scope
from app.core.exceptions import ForbiddenError


# Re-loads the account from the database on every request, so a role change takes
# effect immediately instead of waiting for the token to expire.
def require_permission(permission: Permission):
    async def guard(
        principal: AuthenticatedUser = Depends(get_current_user),
        scope: Scope = Depends(get_scope),
    ) -> AuthenticatedUser:
        auth = scope.resolve(IAuthService)
        fresh = await auth.get_me(principal.id)
        if not has_permission(fresh.role, permission):
            raise ForbiddenError("You don't have permission to do that")
        return AuthenticatedUser(id=fresh.id, role=fresh.role, email=fresh.email)

    return guard
