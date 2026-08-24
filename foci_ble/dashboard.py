from __future__ import annotations

import asyncio
import contextlib
import json
import math
import random
import time
import webbrowser
from pathlib import Path
from typing import Any

from aiohttp import web

from .client import FOCIClient
from .protocol import decode_alert_flags, update_alert_flags

STATIC_DIR = Path(__file__).with_name("static")


class Dashboard:
    def __init__(
        self,
        *,
        address: str | None = None,
        uid: int | None = None,
        write_key: int | None = None,
        demo: bool = False,
    ) -> None:
        self.sockets: set[web.WebSocketResponse] = set()
        self.last_event: dict[str, Any] | None = None
        self.client: FOCIClient | None = None
        self.address = address
        self.uid = uid
        self.write_key = write_key
        self.demo = demo
        self.connection_state = "demo" if demo else "disconnected"
        self.connection_error: str | None = None
        self._connection_lock = asyncio.Lock()
        # These are the values read from this device in both phone captures.
        # A device-status packet will replace them when one is received.
        self.default_flags = 0x0450
        self.session_flags = 0x1010
        self.notification_mode = 0

    async def index(self, _: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        self.sockets.add(socket)
        if self.last_event:
            await socket.send_json(self.last_event)
        try:
            async for _ in socket:
                pass
        finally:
            self.sockets.discard(socket)
        return socket

    async def publish(self, event: dict[str, Any]) -> None:
        if event.get("kind") != "realtime":
            return
        device_config = event.get("device_config")
        if device_config:
            self.default_flags = int(device_config["default_flags"])
            self.session_flags = int(device_config["session_flags"])
            # Only synchronize the form when the device actually reports its
            # configuration. Attaching config to every high-frequency sample
            # would overwrite checkbox edits before the user can save them.
            event["config"] = self.configuration()
        self.last_event = event
        await self.broadcast(event)

    async def broadcast(self, event: dict[str, Any]) -> None:
        dead = []
        for socket in self.sockets:
            try:
                await socket.send_json(event)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.sockets.discard(socket)

    def configuration(self) -> dict[str, Any]:
        connected = bool(
            self.client and self.client.client and self.client.client.is_connected
        )
        if self.demo:
            connected = False
        elif not connected and self.connection_state == "connected":
            self.connection_state = "disconnected"
        return {
            "connected": connected,
            "connection_state": self.connection_state,
            "connection_error": self.connection_error,
            "address": self.client.address if connected and self.client else None,
            "default_flags": self.default_flags,
            "session_flags": self.session_flags,
            "default_alerts": decode_alert_flags(self.default_flags),
            "session_alerts": decode_alert_flags(self.session_flags),
            "deep_work_active": bool(self.notification_mode),
        }

    async def status_api(self, _: web.Request) -> web.Response:
        return web.json_response(self.configuration())

    async def _broadcast_configuration(self) -> None:
        await self.broadcast({"kind": "control", "config": self.configuration()})

    async def on_device_disconnected(self) -> None:
        self.connection_state = "disconnected"
        self.connection_error = "FOCI 蓝牙连接已断开，可以点击按钮重新连接"
        await self._broadcast_configuration()

    async def connect_device(self) -> dict[str, Any]:
        if self.demo:
            raise RuntimeError("演示模式不连接真实 FOCI")
        if self.uid is None or self.write_key is None:
            raise RuntimeError(
                "缺少设备认证信息，请检查项目目录中的 foci.local.json"
            )
        async with self._connection_lock:
            if (
                self.client
                and self.client.client
                and self.client.client.is_connected
            ):
                self.connection_state = "connected"
                self.connection_error = None
                return self.configuration()

            self.connection_state = "connecting"
            self.connection_error = None
            await self._broadcast_configuration()
            candidate = FOCIClient(
                self.address,
                handler=self.publish,
                disconnected_handler=self.on_device_disconnected,
            )
            self.client = candidate
            try:
                await candidate.connect()
                await candidate.start_stream(self.uid, self.write_key)
            except Exception as exc:
                self.client = None
                with contextlib.suppress(Exception):
                    await candidate.disconnect()
                self.connection_state = "error"
                self.connection_error = str(exc)
                await self._broadcast_configuration()
                raise

            self.address = candidate.address
            self.connection_state = "connected"
            self.connection_error = None
            await self._broadcast_configuration()
            return self.configuration()

    async def connect_api(self, _: web.Request) -> web.Response:
        try:
            return web.json_response(await self.connect_device())
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            raise web.HTTPServiceUnavailable(
                text=json.dumps({"error": message}, ensure_ascii=False),
                content_type="application/json",
            ) from exc

    async def _write_configuration(self, *, force_harvest: int = 0) -> None:
        if (
            self.client is None
            or self.client.client is None
            or not self.client.client.is_connected
            or self.uid is None
        ):
            raise web.HTTPServiceUnavailable(
                text=json.dumps(
                    {"error": "FOCI 尚未连接或缺少设备认证信息"},
                    ensure_ascii=False,
                ),
                content_type="application/json",
            )
        try:
            await self.client.set_configuration(
                self.uid,
                default_flags=self.default_flags,
                session_flags=self.session_flags,
                notification_mode=self.notification_mode,
                force_harvest=force_harvest,
            )
        except Exception as exc:
            raise web.HTTPServiceUnavailable(
                text=json.dumps({"error": str(exc)}, ensure_ascii=False),
                content_type="application/json",
            ) from exc
        await self.broadcast({"kind": "control", "config": self.configuration()})

    async def alerts_api(self, request: web.Request) -> web.Response:
        body = await request.json()
        profile = body.get("profile")
        alerts = body.get("alerts")
        if profile not in {"default", "session"} or not isinstance(alerts, dict):
            raise web.HTTPBadRequest(
                text=json.dumps(
                    {"error": "profile 必须是 default/session，并提供 alerts"},
                    ensure_ascii=False,
                ),
                content_type="application/json",
            )
        try:
            if profile == "default":
                self.default_flags = update_alert_flags(self.default_flags, alerts)
            else:
                self.session_flags = update_alert_flags(self.session_flags, alerts)
        except (TypeError, ValueError) as exc:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": str(exc)}, ensure_ascii=False),
                content_type="application/json",
            ) from exc
        await self._write_configuration()
        return web.json_response(self.configuration())

    async def deep_work_api(self, request: web.Request) -> web.Response:
        body = await request.json()
        active = body.get("active")
        if not isinstance(active, bool):
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "active 必须是 true 或 false"}, ensure_ascii=False),
                content_type="application/json",
            )
        self.notification_mode = int(active)
        # The official App raises force_harvest only on session end.
        await self._write_configuration(force_harvest=0 if active else 1)
        return web.json_response(self.configuration())


async def demo_source(dashboard: Dashboard) -> None:
    states = [(5, "calm"), (6, "focused"), (10, "flow"), (4, "distracted")]
    tick = 0
    while True:
        state, label = states[(tick // 20) % len(states)]
        wave = math.sin(tick / 8)
        await dashboard.publish(
            {
                "kind": "realtime",
                "received_at": time.time(),
                "state": state,
                "state_label": label,
                "focus_depth": round(55 + 30 * wave),
                "calm": round(62 + 22 * math.sin(tick / 11 + 1)),
                "signal": round(78 + random.uniform(-4, 4)),
                "signal_quality": round(85 + random.uniform(-3, 3)),
                "mp_score": round(58 + 25 * math.sin(tick / 14)),
                "tension_score": round(33 + 18 * math.sin(tick / 9 + 2)),
            }
        )
        tick += 1
        await asyncio.sleep(0.5)


async def run_dashboard(
    *,
    address: str | None,
    uid: int | None,
    write_key: int | None,
    demo: bool,
    host: str,
    port: int,
    open_browser: bool,
) -> None:
    dashboard = Dashboard(
        address=address,
        uid=uid,
        write_key=write_key,
        demo=demo,
    )
    app = web.Application()
    app.router.add_get("/", dashboard.index)
    app.router.add_get("/ws", dashboard.websocket)
    app.router.add_get("/api/status", dashboard.status_api)
    app.router.add_post("/api/connect", dashboard.connect_api)
    app.router.add_post("/api/alerts", dashboard.alerts_api)
    app.router.add_post("/api/deep-work", dashboard.deep_work_api)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    url = f"http://{host}:{port}"
    print(f"Dashboard: {url}")
    if open_browser:
        webbrowser.open(url)

    source_task: asyncio.Task[Any] | None = None
    if demo:
        source_task = asyncio.create_task(demo_source(dashboard))
    try:
        await asyncio.Event().wait()
    finally:
        if source_task:
            source_task.cancel()
        if dashboard.client:
            await dashboard.client.disconnect()
        await runner.cleanup()
