"""Gateway-side secret drop. Mounted at ``/api/plugins/secret-drop/``.

The desktop half POSTs ``name`` and ``value`` once. This process — the gateway
the Desktop is connected to — writes a private file, stores the value, and
deletes the file. The response does not include the value, and this module
does not log the request body.

``profile`` is the dashboard query parameter. When it names another profile,
the write is scoped to that profile's home instead of the process home.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from secret_drop import SecretDropError, accept_secret_for_profile

router = APIRouter()

# 8192 secret chars plus a JSON envelope. Reject before parsing a huge body.
_MAX_BODY_BYTES = 32_768


@router.post("/drop")
async def drop(request: Request, profile: str | None = None) -> dict:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            too_large = int(length) > _MAX_BODY_BYTES
        except ValueError:
            too_large = True
        if too_large:
            raise HTTPException(status_code=400, detail="secret is too long")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="expected a JSON object") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected a JSON object")
    name = body.get("name")
    value = body.get("value")
    if not isinstance(name, str) or not isinstance(value, str):
        raise HTTPException(status_code=400, detail="name and value are required")
    try:
        return await asyncio.to_thread(accept_secret_for_profile, name, value, profile)
    except HTTPException:
        raise
    except SecretDropError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=400, detail="could not store secret") from None
