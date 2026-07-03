"""S/MIME certificate helpers exposed to the UI.

Unpacking a PKCS#12 (.p12/.pfx) needs the crypto backend, so it happens here; the
resulting cert + key PEM are handed back to the frontend, which stores them in the
local settings blob (same place the OpenPGP keys live). Recipient certificates are
plain PEM the user pastes, validated client-side.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import verify_token

router = APIRouter(prefix="/smime", tags=["smime"], dependencies=[Depends(verify_token)])


class ImportP12In(BaseModel):
    data_b64: str
    password: str = ""


class CertIn(BaseModel):
    cert_pem: str


@router.post("/import-p12")
def import_p12(body: ImportP12In) -> dict:
    """Unpack a .p12/.pfx into PEM cert + key + identity info. The caller persists
    the returned cert/key in the local settings blob."""
    from app.sync import smime as sm
    try:
        data = base64.b64decode(body.data_b64)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Couldn't read the uploaded file.")
    try:
        return sm.load_pkcs12(data, body.password)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/cert-info")
def cert_info(body: CertIn) -> dict:
    """Validate + summarize a pasted recipient certificate (email, subject, validity)."""
    from app.sync import smime as sm
    try:
        return sm.cert_info(body.cert_pem)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a valid PEM X.509 certificate.")
