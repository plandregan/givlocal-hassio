"""LAN discovery of GivEnergy inverters, mirroring GivLocal's discovery screen:
automatic subnet scan on port 8899, manual-subnet override, and manual host entry."""

import asyncio
import logging
import socket
import time

import device_store

logger = logging.getLogger("discovery")

MODBUS_PORT = 8899
SCAN_CONCURRENCY = 40
TCP_PROBE_TIMEOUT = 0.35


def get_local_subnet_prefix() -> str:
    """Best-effort local /24 prefix, e.g. '192.168.0'. Falls back to a common default."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        finally:
            s.close()
        return ".".join(local_ip.split(".")[:3])
    except OSError:
        return "192.168.1"


async def _probe_tcp(host: str, port: int, timeout: float) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
        return True
    except (TimeoutError, OSError):
        return False


async def identify_device(host: str, port: int = MODBUS_PORT) -> dict | None:
    """Connect and run a lightweight detect() to fetch model/serial/firmware for the device list."""
    from givenergy_modbus.client.client import Client

    client = Client(host=host, port=port, connect_timeout=2.0)
    try:
        await client.connect()
        caps = await client.detect(timeout=1.5, retries=1)
        plant = client.plant
        try:
            serial = plant.inverter_serial
        except Exception:
            serial = None
        info = {
            "model": caps.device_type.name,
            "serial": serial,
            "firmware": caps.arm_firmware_version,
        }
        return info
    except Exception:
        logger.debug("identify_device(%s:%s) failed", host, port, exc_info=True)
        return None
    finally:
        await client.close()


class ScanState:
    """Tracks the progress/results of one in-flight or most-recent LAN scan."""

    def __init__(self) -> None:
        self.running = False
        self.subnet_prefix = ""
        self.scanned = 0
        self.total = 254
        self.found: list[dict] = []
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self._task: asyncio.Task | None = None

    def status(self) -> dict:
        return {
            "running": self.running,
            "subnet_prefix": self.subnet_prefix,
            "scanned": self.scanned,
            "total": self.total,
            "found": self.found,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def start(self, subnet_prefix: str | None = None) -> None:
        if self.running:
            return
        self.subnet_prefix = subnet_prefix or get_local_subnet_prefix()
        self.scanned = 0
        self.found = []
        self.running = True
        self.started_at = time.time()
        self.finished_at = None
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        sem = asyncio.Semaphore(SCAN_CONCURRENCY)

        async def scan_one(host: str) -> None:
            async with sem:
                ok = await _probe_tcp(host, MODBUS_PORT, TCP_PROBE_TIMEOUT)
                self.scanned += 1
                if ok:
                    info = await identify_device(host, MODBUS_PORT)
                    device = device_store.upsert_device(
                        host=host,
                        port=MODBUS_PORT,
                        model=(info or {}).get("model"),
                        serial=(info or {}).get("serial"),
                        firmware=(info or {}).get("firmware"),
                    )
                    self.found.append(device)

        hosts = [f"{self.subnet_prefix}.{i}" for i in range(1, 255)]
        try:
            await asyncio.gather(*(scan_one(h) for h in hosts))
        finally:
            self.running = False
            self.finished_at = time.time()


scan_state = ScanState()
