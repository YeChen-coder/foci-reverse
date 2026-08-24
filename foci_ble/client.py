from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from bleak import BleakClient, BleakScanner

from .protocol import (
    CMD_PING,
    OuterFrameAssembler,
    build_challenge,
    build_config_command,
    build_heartbeat,
    build_inner_command,
    build_native_request,
    decode_event,
)

FOCI_SERVICE = "0000fee7-0000-1000-8000-00805f9b34fb"
WRITE_CHAR = "0000fec7-0000-1000-8000-00805f9b34fb"
INDICATE_CHAR = "0000fec8-0000-1000-8000-00805f9b34fb"
READ_CHAR = "0000fec9-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "0000fed8-0000-1000-8000-00805f9b34fb"
DEVICE_NAME_CHAR = "00002a00-0000-1000-8000-00805f9b34fb"

EventHandler = Callable[[dict[str, Any]], None | Awaitable[None]]
DisconnectHandler = Callable[[], None | Awaitable[None]]


async def discover_foci(timeout: float = 8.0) -> list[dict[str, Any]]:
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    results: list[dict[str, Any]] = []
    for device, advertisement in found.values():
        service_uuids = [uuid.lower() for uuid in (advertisement.service_uuids or [])]
        if FOCI_SERVICE not in service_uuids and "foci" not in (
            (device.name or "") + (advertisement.local_name or "")
        ).lower():
            continue
        results.append(
            {
                "address": device.address,
                "name": device.name or advertisement.local_name or "",
                "rssi": advertisement.rssi,
                "service_uuids": service_uuids,
                "device": device,
            }
        )
    results.sort(key=lambda item: item["rssi"], reverse=True)
    return results


async def resolve_target(address: str | None, timeout: float = 8.0) -> Any:
    if address:
        device = await BleakScanner.find_device_by_address(address, timeout=timeout)
        return device or address
    found = await discover_foci(timeout)
    if not found:
        raise RuntimeError(
            "No FOCI advertisement found. Unplug it from the charger, wake it, "
            "and make sure the phone app is disconnected."
        )
    return found[0]["device"]


class FOCIClient:
    def __init__(
        self,
        address: str | None = None,
        *,
        handler: EventHandler | None = None,
        disconnected_handler: DisconnectHandler | None = None,
        scan_timeout: float = 8.0,
    ) -> None:
        self.address = address
        self.handler = handler
        self.disconnected_handler = disconnected_handler
        self.scan_timeout = scan_timeout
        self.client: BleakClient | None = None
        self._assemblers = {
            INDICATE_CHAR: OuterFrameAssembler(),
            NOTIFY_CHAR: OuterFrameAssembler(),
        }
        self._outer_sequence = 1
        self._inner_sequence = 1
        self._heartbeat_task: asyncio.Task[Any] | None = None
        self._write_lock = asyncio.Lock()

    async def __aenter__(self) -> "FOCIClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()

    def _next_outer(self) -> int:
        value = self._outer_sequence & 0xFFFF
        self._outer_sequence += 1
        return value

    def _next_inner(self) -> int:
        value = self._inner_sequence & 0xFFFF
        self._inner_sequence += 1
        return value

    async def connect(self) -> None:
        target = await resolve_target(self.address, self.scan_timeout)
        self.client = BleakClient(
            target,
            timeout=15,
            disconnected_callback=self._disconnected,
        )
        await self.client.connect()
        self.address = self.client.address
        services = {service.uuid.lower() for service in self.client.services}
        if FOCI_SERVICE not in services:
            await self.client.disconnect()
            raise RuntimeError(f"{self.address} does not expose the FOCI FEE7 service")

    def _disconnected(self, _: BleakClient) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self.disconnected_handler is None:
            return
        result = self.disconnected_handler()
        if inspect.isawaitable(result):
            asyncio.create_task(result)

    async def disconnect(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        if self.client and self.client.is_connected:
            for uuid in (INDICATE_CHAR, NOTIFY_CHAR):
                with contextlib.suppress(Exception):
                    await self.client.stop_notify(uuid)
            await self.client.disconnect()

    async def inspect(self) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("not connected")
        name = ""
        read_value = b""
        with contextlib.suppress(Exception):
            name = (await self.client.read_gatt_char(DEVICE_NAME_CHAR)).decode(
                errors="replace"
            ).strip()
        with contextlib.suppress(Exception):
            read_value = bytes(await self.client.read_gatt_char(READ_CHAR))
        services = []
        for service in self.client.services:
            services.append(
                {
                    "uuid": service.uuid,
                    "characteristics": [
                        {"uuid": char.uuid, "properties": list(char.properties)}
                        for char in service.characteristics
                    ],
                }
            )
        return {
            "address": self.address,
            "name": name,
            "connected": self.client.is_connected,
            "mtu": self.client.mtu_size,
            "fec9_hex": read_value.hex(" "),
            "services": services,
        }

    async def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("received_at", time.time())
        if self.handler is None:
            return
        result = self.handler(event)
        if inspect.isawaitable(result):
            await result

    async def _write_packet(self, packet: bytes) -> None:
        """Write using the 20-byte application chunks used by the official App."""
        if not self.client:
            raise RuntimeError("not connected")
        async with self._write_lock:
            for offset in range(0, len(packet), 20):
                await self.client.write_gatt_char(
                    WRITE_CHAR, packet[offset : offset + 20], response=True
                )

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(20)
            await self._write_packet(
                build_heartbeat(int(time.time() * 1000), self._next_outer())
            )

    def _notification(self, sender: Any, data: bytearray) -> None:
        uuid = sender.uuid.lower()
        assembler = self._assemblers.setdefault(uuid, OuterFrameAssembler())
        for frame in assembler.feed(data):
            event = decode_event(frame)
            event["characteristic"] = uuid
            asyncio.create_task(self._emit(event))

    async def start_stream(self, uid: int | None = None, write_key: int | None = None) -> None:
        if not self.client:
            raise RuntimeError("not connected")
        await self.client.start_notify(INDICATE_CHAR, self._notification)
        await self.client.start_notify(NOTIFY_CHAR, self._notification)
        await self._write_packet(build_native_request(self._next_outer()))
        if (uid is None) != (write_key is None):
            raise ValueError("uid and write_key must be supplied together")
        if uid is not None and write_key is not None:
            await asyncio.sleep(0.3)
            challenge = build_challenge(
                uid,
                write_key,
                inner_sequence=self._next_inner(),
                outer_sequence=self._next_outer(),
            )
            await self._write_packet(challenge)
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def ping(self, uid: int) -> None:
        if not self.client:
            raise RuntimeError("not connected")
        packet = build_inner_command(
            CMD_PING,
            uid,
            inner_sequence=self._next_inner(),
            outer_sequence=self._next_outer(),
        )
        await self._write_packet(packet)

    async def set_configuration(
        self,
        uid: int,
        *,
        default_flags: int,
        session_flags: int,
        notification_mode: int = 0,
        pacer_mode: int = 0,
        force_harvest: int = 0,
        mindfulness_level: int = 3,
    ) -> None:
        if not self.client:
            raise RuntimeError("not connected")
        packet = build_config_command(
            uid,
            default_flags=default_flags,
            session_flags=session_flags,
            notification_mode=notification_mode,
            pacer_mode=pacer_mode,
            force_harvest=force_harvest,
            mindfulness_level=mindfulness_level,
            inner_sequence=self._next_inner(),
            outer_sequence=self._next_outer(),
        )
        await self._write_packet(packet)

    async def listen(
        self,
        duration: float = 0,
        *,
        uid: int | None = None,
        write_key: int | None = None,
    ) -> None:
        await self.start_stream(uid, write_key)
        if duration > 0:
            await asyncio.sleep(duration)
        else:
            await asyncio.Event().wait()
