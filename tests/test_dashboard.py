import asyncio

from aiohttp import ClientSession, web

import foci_ble.dashboard as dashboard_module
from foci_ble.dashboard import Dashboard


def test_dashboard_serves_html():
    async def exercise():
        dashboard = Dashboard()
        app = web.Application()
        app.router.add_get("/", dashboard.index)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{port}/") as response:
                    assert response.status == 200
                    html = await response.text()
                    assert "FOCI Desktop" in html
                    assert 'id="connect-btn"' in html
                    assert 'onclick="connectFoci()"' in html
        finally:
            await runner.cleanup()

    asyncio.run(exercise())


def test_connect_device_starts_authenticated_stream(monkeypatch):
    class FakeBleakClient:
        is_connected = True

    class FakeFOCIClient:
        def __init__(
            self,
            address,
            *,
            handler,
            disconnected_handler,
        ):
            self.address = address
            self.handler = handler
            self.disconnected_handler = disconnected_handler
            self.client = None
            self.stream_args = None

        async def connect(self):
            self.address = "synthetic-device"
            self.client = FakeBleakClient()

        async def start_stream(self, uid, write_key):
            self.stream_args = (uid, write_key)

        async def disconnect(self):
            self.client.is_connected = False

    monkeypatch.setattr(dashboard_module, "FOCIClient", FakeFOCIClient)

    async def exercise():
        dashboard = Dashboard(
            address="configured-device",
            uid=123,
            write_key=456,
        )
        result = await dashboard.connect_device()
        assert result["connected"] is True
        assert result["connection_state"] == "connected"
        assert result["address"] == "synthetic-device"
        assert dashboard.client.stream_args == (123, 456)

    asyncio.run(exercise())


def test_connect_device_reports_missing_credentials():
    async def exercise():
        dashboard = Dashboard(address="configured-device")
        try:
            await dashboard.connect_device()
        except RuntimeError as exc:
            assert "foci.local.json" in str(exc)
        else:
            raise AssertionError("connect_device should reject missing credentials")

    asyncio.run(exercise())


def test_connect_api_returns_readable_error():
    async def exercise():
        dashboard = Dashboard(address="configured-device")
        app = web.Application()
        app.router.add_post("/api/connect", dashboard.connect_api)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"http://127.0.0.1:{port}/api/connect",
                    json={},
                ) as response:
                    body = await response.json()
                    assert response.status == 503
                    assert "foci.local.json" in body["error"]
        finally:
            await runner.cleanup()

    asyncio.run(exercise())


def test_realtime_samples_do_not_resynchronize_alert_form():
    async def exercise():
        dashboard = Dashboard()
        ordinary_sample = {"kind": "realtime", "state": 6}
        await dashboard.publish(ordinary_sample)
        assert "config" not in ordinary_sample

        status_sample = {
            "kind": "realtime",
            "state": 2,
            "device_config": {
                "default_flags": 0x0450,
                "session_flags": 0x1010,
            },
        }
        await dashboard.publish(status_sample)
        assert status_sample["config"]["default_alerts"]["focus_slip"] is True
        assert status_sample["config"]["session_alerts"]["early_distraction"] is True

    asyncio.run(exercise())
