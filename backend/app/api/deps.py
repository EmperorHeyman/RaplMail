"""Shared FastAPI dependencies: localhost token auth and secret-store gating."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.security import SecretStore, get_secret_store


async def verify_token(
    x_raplmail_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Reject requests that don't carry the per-launch shared secret.

    When ``settings.token`` is empty (dev mode), the check is skipped.
    """
    if not settings.token:
        return
    if x_raplmail_token != settings.token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad or missing token")


def require_unlocked_store() -> SecretStore:
    """Dependency for endpoints that need credentials; 423 if the vault is locked."""
    store = get_secret_store()
    if not store.is_unlocked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="secret store is locked; unlock with the master password first",
        )
    return store
