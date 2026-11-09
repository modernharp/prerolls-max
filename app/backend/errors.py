"""One error format for the whole API, written for people, not developers.

Every error response looks like this:

    {
      "detail": "Plex didn't answer at http://192.168.1.5:32400.",
      "error": {
        "code": "plex_unreachable",
        "message": "Plex didn't answer at http://192.168.1.5:32400.",
        "hint": "Check that Plex is running and the address is right.",
        "fields": {"url": "..."},          # only for form problems
        "request_id": "a1b2c3d4"
      }
    }

``detail`` stays a plain string so older clients and scripts keep working.
``message`` says what went wrong, ``hint`` says what to do about it, and
``fields`` maps form field names to a message for that field. Technical
details never go in the response: they go to the log under ``request_id`` so
a bug report can quote it.

Raise :class:`AppError` (or one of the helpers) from endpoints. Anything
else that escapes is logged and turned into a generic message.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger("prerollsmax.errors")


from fastapi import HTTPException as _HTTPException


class AppError(_HTTPException):
    """An error whose message is safe and useful to show to the user.

    It is an HTTPException, so the many ``except HTTPException: raise`` blocks
    in older endpoints let it through instead of wrapping it in a 500.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int = 400,
        code: str = "bad_request",
        hint: Optional[str] = None,
        fields: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(status_code=status, detail=message)
        self.message = message
        self.status = status
        self.code = code
        self.hint = hint
        self.fields = dict(fields) if fields else None

    def __str__(self) -> str:
        return self.message

    def body(self, request_id: Optional[str] = None) -> Dict[str, Any]:
        return error_body(self.message, code=self.code, hint=self.hint,
                          fields=self.fields, request_id=request_id)


def error_body(message: str, *, code: str, hint: Optional[str] = None,
               fields: Optional[Mapping[str, str]] = None,
               request_id: Optional[str] = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if hint:
        err["hint"] = hint
    if fields:
        err["fields"] = dict(fields)
    if request_id:
        err["request_id"] = request_id
    return {"detail": message, "error": err}


# ---------------------------------------------------------------------------
# Helpers for the common cases
# ---------------------------------------------------------------------------

def bad_input(message: str, *, field: Optional[str] = None, hint: Optional[str] = None,
              code: str = "invalid_input") -> AppError:
    return AppError(message, status=422, code=code, hint=hint,
                    fields={field: message} if field else None)


def not_found(what: str, *, hint: Optional[str] = None, code: str = "not_found") -> AppError:
    """``what`` is the thing in plain words: "That schedule", "The video"."""
    return AppError(f"{what} doesn't exist anymore. It may have been deleted.",
                    status=404, code=code, hint=hint or "Refresh the page to see the current list.")


def conflict(message: str, *, hint: Optional[str] = None, field: Optional[str] = None,
             code: str = "conflict") -> AppError:
    return AppError(message, status=409, code=code, hint=hint,
                    fields={field: message} if field else None)


def unreachable(service: str, address: Optional[str] = None, *, hint: Optional[str] = None,
                code: Optional[str] = None) -> AppError:
    where = f" at {address}" if address else ""
    return AppError(
        f"{service} didn't answer{where}.",
        status=502,
        code=code or f"{_slug(service)}_unreachable",
        hint=hint or f"Check that {service} is running and that the address is right.",
    )


def rejected_credentials(service: str, *, what: str = "token", hint: Optional[str] = None) -> AppError:
    return AppError(
        f"{service} turned down the {what}.",
        status=401 if service == "Prerolls Max" else 502,
        code=f"{_slug(service)}_auth_failed",
        hint=hint or f"Copy the {what} again from {service} and paste it in. Extra spaces are removed for you.",
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "service"


# ---------------------------------------------------------------------------
# Validation messages (422)
# ---------------------------------------------------------------------------

_TYPE_MESSAGES = {
    "missing": "This is required.",
    "string_too_short": "This is too short.",
    "string_too_long": "This is too long.",
    "int_parsing": "Enter a whole number.",
    "int_type": "Enter a whole number.",
    "float_parsing": "Enter a number.",
    "float_type": "Enter a number.",
    "bool_parsing": "Choose yes or no.",
    "bool_type": "Choose yes or no.",
    "greater_than_equal": "This number is too small.",
    "greater_than": "This number is too small.",
    "less_than_equal": "This number is too big.",
    "less_than": "This number is too big.",
    "literal_error": "Pick one of the options.",
    "enum": "Pick one of the options.",
    "date_parsing": "Enter a date like 2026-12-24.",
    "date_from_datetime_parsing": "Enter a date like 2026-12-24.",
    "datetime_parsing": "Enter a date and time like 2026-12-24 18:30.",
    "datetime_from_date_parsing": "Enter a date and time like 2026-12-24 18:30.",
    "time_parsing": "Enter a time like 18:30.",
    "url_parsing": "Enter a full web address, like http://192.168.1.10:32400.",
    "url_scheme": "The address must start with http:// or https://.",
    "list_type": "This should be a list.",
    "dict_type": "This should be a group of settings.",
    "json_invalid": "The request wasn't valid JSON.",
    "extra_forbidden": "This setting isn't recognised.",
    "string_pattern_mismatch": "This isn't in the right format.",
}


def _field_name(loc) -> str:
    # Only the first part says where the value came from; a field may itself
    # be called "path" (a folder) or "query" (a search).
    parts = [str(p) for p in loc]
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        parts = parts[1:]
    return ".".join(parts) or "request"


def friendly_validation_fields(errors) -> Dict[str, str]:
    """Turn pydantic/FastAPI validation errors into {field: plain message}."""
    fields: Dict[str, str] = {}
    for err in errors or []:
        name = _field_name(err.get("loc") or ())
        etype = err.get("type") or ""
        msg = err.get("msg") or ""
        if etype == "value_error":
            # Our own validators raise ValueError with a finished sentence.
            text = msg.split(",", 1)[1].strip() if msg.lower().startswith("value error,") else msg
        else:
            text = _TYPE_MESSAGES.get(etype)
            ctx = err.get("ctx") or {}
            if etype == "string_too_short" and "min_length" in ctx:
                n = ctx["min_length"]
                text = "This is required." if n == 1 else f"Use at least {n} characters."
            elif etype == "string_too_long" and "max_length" in ctx:
                text = f"Use {ctx['max_length']} characters or fewer."
            elif etype in ("greater_than_equal", "greater_than") and ("ge" in ctx or "gt" in ctx):
                text = f"Use {ctx.get('ge', ctx.get('gt'))} or more."
            elif etype in ("less_than_equal", "less_than") and ("le" in ctx or "lt" in ctx):
                text = f"Use {ctx.get('le', ctx.get('lt'))} or less."
            elif etype == "literal_error" and "expected" in ctx:
                text = f"Pick one of: {ctx['expected']}."
            if not text:
                text = "This value isn't valid."
        fields.setdefault(name, text)
    return fields


def validation_summary(fields: Mapping[str, str]) -> str:
    if len(fields) == 1:
        (name, text), = fields.items()
        label = name.replace("_", " ").replace(".", " ")
        return f"Check the {label} field: {text}"
    return f"{len(fields)} fields need a fix before this can be saved."


# ---------------------------------------------------------------------------
# Raw exception text: keep it out of responses
# ---------------------------------------------------------------------------

_TECHNICAL = re.compile(
    r"Traceback|Errno|errno|sqlalchemy|sqlite3\.|psycopg|Exception\(|Error\(|"
    r"object at 0x|NoneType|KeyError|AttributeError|TypeError|ValueError|"
    r"HTTPSConnectionPool|HTTPConnectionPool|Max retries|urllib3|httpx\.|"
    r"\[SQL:|File \"|line \d+, in ",
)


def looks_technical(text: str) -> bool:
    return bool(text) and bool(_TECHNICAL.search(text))


GENERIC_MESSAGE = "Something went wrong on our side."
GENERIC_HINT = ("Try again in a moment. If it keeps happening, open Settings > Logs and "
                "send the entry with this reference number when you report it.")


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def install(app, log=None) -> None:
    """Register handlers on a FastAPI app. ``log(message, level)`` is optional."""
    from fastapi import HTTPException, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    def _log(message: str, level: str = "ERROR") -> None:
        if log:
            try:
                log(message, level)
                return
            except Exception:
                pass
        logger.log(logging.ERROR if level == "ERROR" else logging.WARNING, message)

    def _rid(request) -> str:
        rid = getattr(request.state, "request_id", None)
        if not rid:
            rid = new_request_id()
            request.state.request_id = rid
        return rid

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):
        request.state.request_id = new_request_id()
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request.state.request_id)
        return response

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        rid = _rid(request)
        if exc.status >= 500:
            _log(f"[{rid}] {request.method} {request.url.path}: {exc.code}: {exc.message}")
        return JSONResponse(exc.body(rid), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        rid = _rid(request)
        fields = friendly_validation_fields(exc.errors())
        _log(f"[{rid}] validation {request.method} {request.url.path}: {fields}", "WARNING")
        body = error_body(validation_summary(fields), code="invalid_input",
                          fields=fields, request_id=rid)
        return JSONResponse(body, status_code=422)

    async def _http_error(request: Request, exc):
        rid = _rid(request)
        status = getattr(exc, "status_code", 500)
        detail = getattr(exc, "detail", None)
        headers = getattr(exc, "headers", None)
        # Some endpoints already return a structured body; pass it through.
        if isinstance(detail, dict) and "message" in detail:
            body = error_body(str(detail["message"]), code=str(detail.get("code") or "error"),
                              hint=detail.get("hint"), fields=detail.get("fields"), request_id=rid)
            return JSONResponse(body, status_code=status, headers=headers)
        if isinstance(detail, list):  # old-style validation lists
            fields = friendly_validation_fields(detail)
            body = error_body(validation_summary(fields), code="invalid_input", fields=fields,
                              request_id=rid)
            return JSONResponse(body, status_code=status, headers=headers)
        text = str(detail) if detail is not None else ""
        if status >= 500 or looks_technical(text):
            _log(f"[{rid}] {request.method} {request.url.path} -> {status}: {text}")
            if looks_technical(text) or not text:
                return JSONResponse(error_body(GENERIC_MESSAGE, code="server_error",
                                               hint=GENERIC_HINT, request_id=rid),
                                    status_code=status, headers=headers)
        code = {400: "bad_request", 401: "login_required", 403: "not_allowed", 404: "not_found",
                405: "not_allowed", 409: "conflict", 413: "too_large", 422: "invalid_input",
                429: "too_many_requests"}.get(status, "error")
        if not text:
            text = {401: "Please sign in first.", 403: "Your account can't do that.",
                    404: "That page or item doesn't exist.", 405: "That action isn't allowed here.",
                    413: "That file is too big.", 429: "Too many requests. Wait a moment and try again."
                    }.get(status, "That didn't work.")
        return JSONResponse(error_body(text, code=code, request_id=rid), status_code=status,
                            headers=headers)

    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        rid = _rid(request)
        import traceback
        _log(f"[{rid}] unhandled {request.method} {request.url.path}: "
             f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        return JSONResponse(error_body(GENERIC_MESSAGE, code="server_error", hint=GENERIC_HINT,
                                       request_id=rid), status_code=500)
