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
import json
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

_ROUTER_ROOT = Path(__file__).resolve().parents[1]
if str(_ROUTER_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROUTER_ROOT))

from secret_drop import SecretDropError, accept_secret_for_profile

logger = logging.getLogger(__name__)

router = APIRouter()

# 8192 secret chars plus a JSON envelope. The cap is enforced while the body
# streams, so a chunked request without Content-Length is cut off early too.
_MAX_BODY_BYTES = 32_768


@router.post("/drop")
async def drop(request: Request, profile: str | None = None) -> dict:
    body = await _read_json_body(request)
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
    except Exception as exc:
        logger.warning("secret drop request failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=400, detail="could not store secret") from None


async def _read_json_body(request: Request) -> object:
    """Read the request body under a hard byte cap, then parse it as JSON.

    A declared Content-Length above the cap is rejected before any read. Without the
    header (chunked upload) the stream is consumed incrementally and aborted the moment
    the cap is crossed, so an oversized body is never buffered or parsed.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            too_large = int(declared) > _MAX_BODY_BYTES
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content length") from None
        if too_large:
            raise HTTPException(status_code=413, detail="secret is too long")
    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            total += len(chunk)
            if total > _MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="secret is too long")
            chunks.append(bytes(chunk))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="could not read request body") from None
    try:
        return json.loads(b"".join(chunks))
    except Exception:
        raise HTTPException(status_code=400, detail="expected a JSON object") from None
