# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from .domain import Task
from .store import Store, Conflict
from .calendars import fetch

identity = ContextVar("identity", default=None)


class Progress(BaseModel):
    session_id: str = Field(min_length=1, max_length=150)
    minutes: int = Field(ge=0, le=10080, strict=True)


def create_app(config=None):
    cfg = dict(config or {})
    data = Path(cfg.get("data", os.environ.get("INTERSTICE_DATA", "/data")))
    zone = cfg.get("zone", os.environ.get("INTERSTICE_ZONE", "Europe/Berlin"))
    public = cfg.get("public_url", os.environ.get("INTERSTICE_PUBLIC_URL", "http://localhost:8095"))
    parsed = urlsplit(public)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    prefix = parsed.path.rstrip("/")
    token_file = cfg.get("tokens_file", os.environ.get("INTERSTICE_TOKENS_FILE", "/run/secrets/tokens.json"))
    clients = cfg.get("clients") or json.loads(Path(token_file).read_text())
    for client in clients:
        if len(client["token"]) < 32 or client["role"] not in ("admin", "read"):
            raise RuntimeError("Invalid client credential configuration")
    if len({c["id"] for c in clients}) != len(clients):
        raise RuntimeError("Duplicate client identities")
    store = Store(data / "interstice.sqlite", zone)
    sources_file = cfg.get("sources_file", os.environ.get("INTERSTICE_SOURCES_FILE", ""))
    sources = json.loads(Path(sources_file).read_text()) if sources_file else []
    if len(sources) > 10 or len({s["id"] for s in sources}) != len(sources):
        raise RuntimeError("Invalid sources configuration")
    gateway = cfg.get("model_url", os.environ.get("INTERSTICE_MODEL_URL", ""))
    model = cfg.get("model", os.environ.get("INTERSTICE_MODEL", ""))
    model_protocol = cfg.get("model_protocol", os.environ.get("INTERSTICE_MODEL_PROTOCOL", "ollama"))
    model_key_file = os.environ.get("INTERSTICE_MODEL_KEY_FILE", "")
    if gateway:
        endpoint = urlsplit(gateway)
        if endpoint.scheme not in ("http", "https") or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise RuntimeError("Invalid configured inference endpoint")
        if endpoint.scheme == "http" and not cfg.get("allow_private_model", os.environ.get("INTERSTICE_ALLOW_PRIVATE_MODEL") == "1"):
            raise RuntimeError("Private HTTP inference requires explicit configuration")
    model_lock = asyncio.Lock()
    sync_lock = asyncio.Lock()
    last_model = [0.0]
    sessions = {}
    limits = {}

    async def sync_sources():
        async with sync_lock:
            for source in sources:
                try:
                    store.source_result(source["id"], events=await fetch(source))
                except Exception:
                    # Exception strings may contain credential-bearing URLs.
                    store.source_result(source["id"], error="Refresh failed; prior snapshot retained")

    async def polling():
        while True:
            await sync_sources()
            await asyncio.sleep(300)

    mcp = FastMCP("Etabli Interstice test", stateless_http=True, json_response=True,
                  transport_security=TransportSecuritySettings(allowed_hosts=[parsed.netloc, "localhost:*", "127.0.0.1:*", "testserver"],
                                                                allowed_origins=[origin]))

    def require_write():
        caller = identity.get()
        if not caller or caller["role"] != "admin":
            raise PermissionError("Write scope is required")
        return caller["id"]

    @mcp.tool()
    def tasks_list() -> dict:
        """List tasks in this isolated test instance."""
        return {"tasks": store.tasks(), "mode": "test"}

    @mcp.tool()
    def schedule_get() -> dict:
        """Preview the deterministic schedule; never writes external calendars."""
        return store.plan()

    @mcp.tool()
    def task_create(task: Task, idempotency_key: str) -> dict:
        """Create a test task. Requires granted write scope."""
        return store.mutate(require_write(), idempotency_key, "create", task.model_dump(mode="json"))

    @mcp.tool()
    def task_progress(task_id: str, session_id: str, minutes: int, idempotency_key: str) -> dict:
        """Credit cumulative productive minutes for a stable session, without duplicate credit."""
        progress = Progress(session_id=session_id, minutes=minutes)
        return store.mutate(require_write(), idempotency_key, "progress", progress.model_dump(), ident=task_id)

    @mcp.tool()
    def task_complete(task_id: str, revision: int, idempotency_key: str) -> dict:
        """Explicitly complete a test task with revision and duplicate protection."""
        return store.mutate(require_write(), idempotency_key, "complete", {}, ident=task_id, revision=revision)

    @mcp.tool()
    def operation_get(idempotency_key: str) -> dict:
        """Read this client's durable mutation receipt."""
        return store.operation(identity.get()["id"], idempotency_key)

    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            poll = asyncio.create_task(polling())
            yield
            poll.cancel()
            try:
                await poll
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="Établi Interstice test", version="0.1.0-test", root_path=prefix,
                  lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        message = "Invalid task or request" if isinstance(exc, ValidationError) else str(exc)
        return JSONResponse({"detail": message}, status_code=409 if isinstance(exc, Conflict) else 422)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Record not found"}, status_code=404)

    @app.exception_handler(PermissionError)
    async def forbidden(request, exc):
        return JSONResponse({"detail": "Write scope required"}, status_code=403)

    @app.middleware("http")
    async def security(request, call_next):
        # A stripping reverse proxy removes the prefix from path. Mounted ASGI
        # applications need the full path as well as root_path to resolve assets.
        if prefix and not request.scope["path"].startswith(prefix + "/"):
            request.scope["path"] = prefix + request.scope["path"]
            request.scope["raw_path"] = prefix.encode() + request.scope.get("raw_path", b"/")
        if request.headers.get("host", "").split(":")[0] not in (parsed.hostname, "localhost", "127.0.0.1", "testserver"):
            return JSONResponse({"detail": "Invalid host"}, status_code=400)
        path = request.url.path
        # Starlette may include root_path in the request URL depending on the proxy.
        if prefix and path.startswith(prefix + "/"):
            path = path[len(prefix):]
        ip = request.client.host if request.client else "unknown"
        minute = int(time.monotonic() // 60)
        if len(limits) > 10000:
            limits.clear()
        key = (ip, minute)
        limits[key] = limits.get(key, 0) + 1
        if limits[key] > 240:
            return JSONResponse({"detail": "Rate limit"}, status_code=429)
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        if content_length > 100000:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        if request.method in ("POST", "PATCH", "PUT"):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 100000:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            request._body = bytes(body)
        caller = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            candidate = auth[7:]
            caller = next((c for c in clients if secrets.compare_digest(candidate, c["token"])), None)
        elif path != "/mcp":
            session = sessions.get(request.cookies.get("interstice_session", ""))
            if session and session[1] > time.time():
                caller = session[0]
                if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("origin") != origin:
                    return JSONResponse({"detail": "Origin required"}, status_code=403)
        protected = path.startswith("/api/") or path.startswith("/mcp")
        if protected and caller is None:
            return JSONResponse({"detail": "Sign in required"}, status_code=401)
        context_token = identity.set(caller)
        try:
            response = await call_next(request)
        finally:
            identity.reset(context_token)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.post("/login")
    async def login(request: Request):
        if request.headers.get("origin") != origin:
            raise HTTPException(403, "Origin required")
        body = await request.json()
        value = body.get("token", "")
        if not isinstance(value, str):
            raise HTTPException(401, "Invalid credential")
        caller = next((c for c in clients if secrets.compare_digest(value, c["token"])), None)
        if not caller:
            await asyncio.sleep(0.3)
            raise HTTPException(401, "Invalid credential")
        if len(sessions) > 100:
            sessions.clear()
        session = secrets.token_urlsafe(32)
        sessions[session] = (caller, time.time() + 28800)
        response = JSONResponse({"ok": True})
        response.set_cookie("interstice_session", session, max_age=28800, httponly=True, secure=parsed.scheme == "https", samesite="strict", path=prefix or "/")
        return response

    @app.post("/api/v1/logout")
    async def logout(request: Request):
        sessions.pop(request.cookies.get("interstice_session", ""), None)
        response = JSONResponse({"ok": True})
        response.delete_cookie("interstice_session", path=prefix or "/")
        return response

    @app.get("/health/live")
    @app.get("/health/ready")
    def health():
        with store.db() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "mode": "test", "calendar_writes": False, "version": "0.1.0-test"}

    @app.get("/api/v1/status")
    def status():
        return {"mode": "test", "calendar_writes": False, "role": identity.get()["role"], "time_zone": zone,
                "model_configured": bool(gateway and model), "model": model or None,
                "source": "https://github.com/etabli-dev/etabli-interstice", "version": "0.1.0-test",
                "limitations": ["No production calendar writes", "No recurring tasks yet", "Focus adapter not installed", "Preview recalculates from current inputs"]}

    @app.get("/api/v1/tasks")
    def tasks():
        return {"tasks": store.tasks()}

    @app.post("/api/v1/tasks")
    def create(task: Task, request: Request):
        return store.mutate(require_write(), request.headers.get("Idempotency-Key"), "create", task.model_dump(mode="json"))

    @app.patch("/api/v1/tasks/{ident}")
    async def update(ident: str, request: Request):
        body = await request.json()
        return store.mutate(require_write(), request.headers.get("Idempotency-Key"), "update", body, ident=ident, revision=int(request.headers.get("If-Match", "-1")))

    @app.post("/api/v1/tasks/{ident}/progress")
    def progress(ident: str, body: Progress, request: Request):
        return store.mutate(require_write(), request.headers.get("Idempotency-Key"), "progress", body.model_dump(), ident=ident)

    @app.post("/api/v1/tasks/{ident}/complete")
    def complete(ident: str, request: Request):
        return store.mutate(require_write(), request.headers.get("Idempotency-Key"), "complete", {}, ident=ident, revision=int(request.headers.get("If-Match", "-1")))

    @app.get("/api/v1/operations/{key}")
    def receipt(key: str):
        return store.operation(identity.get()["id"], key)

    @app.get("/api/v1/schedule")
    def plan():
        return store.plan()

    @app.post("/api/v1/calendars/refresh")
    async def sync():
        require_write()
        await sync_sources()
        return store.plan()["sources"]

    @app.post("/api/v1/model/propose")
    async def propose(request: Request):
        require_write()
        if not gateway or not model:
            raise HTTPException(503, "No model endpoint configured")
        body = await request.json()
        text = body.get("text", "")
        if not isinstance(text, str) or not 1 <= len(text) <= 3000:
            raise HTTPException(422, "Enter a request of 1–3000 characters")
        if model_lock.locked() or time.monotonic() - last_model[0] < 15:
            raise HTTPException(429, "Model busy; try again shortly")
        async with model_lock:
            last_model[0] = time.monotonic()
            prompt = ("Return only one JSON object for a task draft. Fields: title (string), minutes (integer 1..10080), "
                      "priority (integer 0..3), notes (string), due (ISO datetime with offset or null). "
                      "Never invent a deadline; use null if uncertain. Do not execute actions. "
                      f"Current UTC time: {datetime.now(timezone.utc).isoformat()}. User zone: {zone}.")
            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": text}]
            headers = {}
            if model_key_file:
                headers["Authorization"] = "Bearer " + Path(model_key_file).read_text().strip()
            if model_protocol == "ollama":
                url = gateway.rstrip("/") + "/api/chat"
                payload = {"model": model, "messages": messages, "stream": False, "format": "json", "think": False, "keep_alive": "1m",
                           "options": {"num_ctx": 2048, "num_predict": 256, "num_thread": 1, "temperature": 0}}
            elif model_protocol == "chat-completions":
                url = gateway.rstrip("/") + "/chat/completions"
                payload = {"model": model, "messages": messages, "max_tokens": 500, "temperature": 0,
                           "response_format": {"type": "json_object"}}
            else:
                raise HTTPException(503, "Unsupported configured model protocol")
            try:
                async with httpx.AsyncClient(timeout=120, follow_redirects=False, trust_env=False) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as response:
                        response.raise_for_status()
                        raw = bytearray()
                        async for part in response.aiter_bytes():
                            raw.extend(part)
                            if len(raw) > 100000:
                                raise ValueError("Oversize model response")
                        output = json.loads(raw)
                content = output["message"]["content"] if model_protocol == "ollama" else output["choices"][0]["message"]["content"]
                draft = Task.model_validate(json.loads(content)).model_dump(mode="json")
            except Exception:
                raise HTTPException(502, "Model unavailable or returned invalid task data; no task was created")
            return {"proposal": draft, "applied": False, "model": model}

    @app.get("/")
    def index():
        return FileResponse(Path(__file__).parent / "static/index.html")

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"))
    app.mount("/", mcp_app)
    return app
