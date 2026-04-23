"""Shared msgpack transport helpers for v2 HTTP endpoints.

Clients negotiate msgpack via `Accept: application/msgpack` for responses and
`Content-Type: application/msgpack` for request bodies. JSON stays fully
supported as a fallback so curl / browsers without msgpack still work.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import msgpack
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError


def _accepts_msgpack(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "msgpack" in accept.lower()


class MsgPackResponse(JSONResponse):
    """Response that switches between msgpack and JSON based on Accept header."""

    def __init__(self, content: Any, request: Request, status_code: int = 200) -> None:
        self._use_msgpack = _accepts_msgpack(request)
        if self._use_msgpack:
            self._packed = msgpack.packb(content, use_single_float=True)
        super().__init__(
            content,
            status_code=status_code,
            media_type="application/msgpack" if self._use_msgpack else None,
        )

    def render(self, content: Any) -> bytes:
        if self._use_msgpack:
            return self._packed
        return super().render(content)


def msgpack_body(model: type[BaseModel]) -> Callable[..., Any]:
    """FastAPI dependency: parse a request body as msgpack or JSON into `model`.

    Use in place of `Body(...)` so endpoints accept both encodings based on
    `Content-Type`. Validation errors bubble up as 422 with Pydantic details.
    """

    async def _parse(request: Request) -> BaseModel:
        raw = await request.body()
        content_type = request.headers.get("content-type", "").lower()
        try:
            if content_type.startswith("application/msgpack"):
                data = msgpack.unpackb(raw, raw=False) if raw else {}
                return model.model_validate(data)
            if not raw:
                return model.model_validate({})
            return model.model_validate_json(raw)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid body: {exc}") from exc

    return Depends(_parse)


__all__ = ["MsgPackResponse", "_accepts_msgpack", "msgpack_body"]
