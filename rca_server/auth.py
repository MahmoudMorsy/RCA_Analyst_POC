from __future__ import annotations

import hmac
import os

from typing import Optional

from fastapi import Header, HTTPException, status

from .backend_config import BackendSettings


class AuthGuard:
    def __init__(self, settings: BackendSettings):
        self.settings = settings

    async def __call__(self, authorization: Optional[str] = Header(default=None)) -> None:
        if not self.settings.deployment.auth_required:
            return
        expected = os.environ.get("RCA_API_TOKEN", "")
        if not expected:
            raise HTTPException(status_code=503, detail="Remote authentication is enabled but RCA_API_TOKEN is not configured")
        supplied = ""
        if authorization and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing bearer token")
