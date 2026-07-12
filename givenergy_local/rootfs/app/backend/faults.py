"""Fault history tracking, mirroring GivLocal's Fault Log: the inverter doesn't expose
fault event timestamps over Modbus, so detected/cleared times are recorded locally as
of when this add-on's poll loop first observed each fault name, persisted under /data
so history survives a restart.
"""

import json
import os
import threading
import time

import device_store

FAULTS_FILE = os.path.join(device_store.DATA_DIR, "faults.json")
_lock = threading.Lock()


def _load() -> dict:
    os.makedirs(device_store.DATA_DIR, exist_ok=True)
    if not os.path.exists(FAULTS_FILE):
        return {}
    with open(FAULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(device_store.DATA_DIR, exist_ok=True)
    tmp = FAULTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FAULTS_FILE)


def record(device_key: str, active_faults: list[str]) -> list[dict]:
    """Update history for device_key given the currently-active fault names; returns the log."""
    with _lock:
        data = _load()
        history = data.setdefault(device_key, [])
        now = time.time()
        active_set = set(active_faults)
        open_entries = {e["name"]: e for e in history if e["cleared_at"] is None}

        for name in active_set - open_entries.keys():
            history.append({"name": name, "detected_at": now, "cleared_at": None})

        for name, entry in open_entries.items():
            if name not in active_set:
                entry["cleared_at"] = now

        data[device_key] = history
        _save(data)
        return history


def get_log(device_key: str) -> list[dict]:
    with _lock:
        return _load().get(device_key, [])


def clear_entry(device_key: str, index: int) -> bool:
    with _lock:
        data = _load()
        history = data.get(device_key, [])
        if 0 <= index < len(history):
            del history[index]
            data[device_key] = history
            _save(data)
            return True
        return False
