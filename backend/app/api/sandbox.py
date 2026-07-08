"""Deep attachment analysis endpoint for the WebAssembly sandbox window.

The sandbox window itself is isolated (no backend access), so the main window
POSTs the file bytes here, gets back the deep report (macro de-obfuscation, PDF
stream decompression), and hands it to the sandbox via its seed. Analysis is
extraction/decoding only - nothing is ever executed.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import verify_token
from app.core.deepscan import deep_analyze

router = APIRouter(prefix="/sandbox", tags=["sandbox"], dependencies=[Depends(verify_token)])

# Guard against unbounded work; the wasm sandbox caps at 8 MB anyway.
_MAX = 12 * 1024 * 1024
# Wall-clock ceiling: a crafted file must never hang the scan (which now runs
# automatically in the background). If olevba/inflate exceed this, we bail with
# a "timed out" report rather than blocking. The worker thread is left to finish
# on its own; a single dedicated executor bounds concurrent parses.
_TIMEOUT_S = 15
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="deepscan")


class AnalyzeIn(BaseModel):
    filename: str = "file"
    data_b64: str = ""


@router.post("/analyze")
def analyze(body: AnalyzeIn) -> dict:
    try:
        data = base64.b64decode(body.data_b64 or "", validate=False)
    except Exception:
        data = b""
    if len(data) > _MAX:
        data = data[:_MAX]
    fname = body.filename or "file"
    try:
        return _pool.submit(deep_analyze, fname, data).result(timeout=_TIMEOUT_S)
    except FuturesTimeout:
        return {"ran": False, "office": None, "pdf": None, "score": 0,
                "summary": [], "timeout": True}
