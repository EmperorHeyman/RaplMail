"""Master-password lifecycle for the encrypted secret store."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import verify_token
from app.core.security import BadPasswordError, SecretStore, SecretStoreError, get_secret_store

router = APIRouter(prefix="/vault", tags=["vault"], dependencies=[Depends(verify_token)])


class PasswordIn(BaseModel):
    password: str


class ChangePasswordIn(BaseModel):
    new_password: str


class VaultStatus(BaseModel):
    exists: bool
    unlocked: bool
    auto_unlock: bool = False


def _status(store: SecretStore) -> VaultStatus:
    return VaultStatus(exists=store.exists, unlocked=store.is_unlocked,
                       auto_unlock=store.auto_unlock_enabled)


@router.get("/status", response_model=VaultStatus)
def status_(store: SecretStore = Depends(get_secret_store)) -> VaultStatus:
    return _status(store)


class AutoUnlockIn(BaseModel):
    enabled: bool
    password: str = ""  # required when enabling


@router.post("/auto-unlock", response_model=VaultStatus)
def set_auto_unlock(body: AutoUnlockIn, store: SecretStore = Depends(get_secret_store)) -> VaultStatus:
    try:
        if body.enabled:
            store.enable_auto_unlock(body.password)
        else:
            store.disable_auto_unlock()
    except BadPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except SecretStoreError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _status(store)


@router.post("/initialize", response_model=VaultStatus)
def initialize(body: PasswordIn, store: SecretStore = Depends(get_secret_store)) -> VaultStatus:
    try:
        store.initialize(body.password)
    except SecretStoreError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _status(store)


@router.post("/unlock", response_model=VaultStatus)
def unlock(body: PasswordIn, store: SecretStore = Depends(get_secret_store)) -> VaultStatus:
    try:
        store.unlock(body.password)
    except BadPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except SecretStoreError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _status(store)


@router.post("/lock", response_model=VaultStatus)
def lock(store: SecretStore = Depends(get_secret_store)) -> VaultStatus:
    store.lock()
    return _status(store)


@router.post("/change-password", response_model=VaultStatus)
def change_password(body: ChangePasswordIn, store: SecretStore = Depends(get_secret_store)) -> VaultStatus:
    try:
        store.change_password(body.new_password)
    except SecretStoreError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc
    return _status(store)
