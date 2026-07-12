"""Persisted device list — known/favourite inverters, mirroring GivLocal's
local-only (no cloud) device management. Stored as JSON under the add-on's
persistent /data directory (or ./data when run standalone for development)."""

import json
import os
import threading
import time
import uuid

DATA_DIR = os.environ.get("GIVLOCAL_DATA_DIR", "./data")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")

_lock = threading.Lock()


def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not os.path.exists(DEVICES_FILE):
        return {"devices": {}}
    with open(DEVICES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    _ensure_dir()
    tmp = DEVICES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DEVICES_FILE)


def list_devices() -> list[dict]:
    with _lock:
        return list(_load()["devices"].values())


def get_device(device_id: str) -> dict | None:
    with _lock:
        return _load()["devices"].get(device_id)


def upsert_device(host: str, port: int = 8899, model: str | None = None, serial: str | None = None,
                   firmware: str | None = None) -> dict:
    """Add a newly-seen device, or update an existing one matched by host:port."""
    with _lock:
        data = _load()
        existing = next(
            (d for d in data["devices"].values() if d["host"] == host and d["port"] == port), None
        )
        now = time.time()
        if existing:
            existing.update(
                {k: v for k, v in {"model": model, "serial": serial, "firmware": firmware}.items() if v is not None}
            )
            existing["last_seen"] = now
            data["devices"][existing["id"]] = existing
            _save(data)
            return existing
        device_id = uuid.uuid4().hex[:12]
        device = {
            "id": device_id,
            "host": host,
            "port": port,
            "custom_name": None,
            "model": model,
            "serial": serial,
            "firmware": firmware,
            "favourite": False,
            "added_at": now,
            "last_seen": now,
            "last_connected": None,
        }
        data["devices"][device_id] = device
        _save(data)
        return device


def update_device(device_id: str, **fields) -> dict | None:
    with _lock:
        data = _load()
        device = data["devices"].get(device_id)
        if device is None:
            return None
        device.update(fields)
        data["devices"][device_id] = device
        _save(data)
        return device


def delete_device(device_id: str) -> bool:
    with _lock:
        data = _load()
        if device_id in data["devices"]:
            del data["devices"][device_id]
            _save(data)
            return True
        return False


def set_favourite(device_id: str) -> dict | None:
    with _lock:
        data = _load()
        if device_id not in data["devices"]:
            return None
        for d in data["devices"].values():
            d["favourite"] = d["id"] == device_id
        _save(data)
        return data["devices"][device_id]


def get_favourite() -> dict | None:
    with _lock:
        data = _load()
        return next((d for d in data["devices"].values() if d.get("favourite")), None)


def mark_connected(device_id: str) -> None:
    update_device(device_id, last_connected=time.time())
