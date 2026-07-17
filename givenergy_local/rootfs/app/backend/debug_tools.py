"""Expert/debug tools: raw register read/write, arbitrary hex frame injection, and
a raw TX/RX frame log — for diagnosing protocol issues or exploring undocumented
registers, mirroring GivLocal's Register Reader / Write Log / Verbose Frame Logging.

Register reads are unrestricted (the library doesn't gate reads). Register writes
still go through the library's structured PDU path, which enforces its own
known-safe-register allowlist at the encode() step regardless of entry point — so
a write to a register outside that allowlist will be rejected here too. That's a
deliberate floor in givenergy-modbus, not a limitation of this add-on; the raw hex
command below is the escape hatch for anything not on the list, and bypasses the
library entirely (raw bytes straight to the socket, no framing/safety of any kind).
"""

from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.pdu import ReadHoldingRegistersRequest, ReadInputRegistersRequest
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest

from plant import PlantSession

DEFAULT_SLAVE = 0x11


def _slave_or_default(session: PlantSession, slave: int | None) -> int:
    if slave is not None:
        return slave
    caps = session.client.plant.capabilities
    return caps.inverter_address if caps else DEFAULT_SLAVE


async def read_registers(
    session: PlantSession, reg_type: str, address: int, count: int, slave: int | None
) -> list[int]:
    device_address = _slave_or_default(session, slave)
    cls = ReadHoldingRegistersRequest if reg_type == "HR" else ReadInputRegistersRequest
    request = cls(base_register=address, register_count=count, device_address=device_address)
    response = await session.client.send_request_and_await_response(request, timeout=3.0, retries=1)
    return list(response.register_values)


async def write_register(session: PlantSession, address: int, value: int, slave: int | None) -> None:
    """Try the register as installer-tier first, then plain-safe. Neither succeeding
    means it's outside both of the library's known-writable sets — use the raw hex
    command for anything not on either list."""
    device_address = _slave_or_default(session, slave)
    last_error: Exception | None = None
    for installer_flag in (True, False):
        req = WriteHoldingRegisterRequest(address, value, installer=installer_flag, device_address=device_address)
        try:
            await session.client.execute([req], timeout=3.0, retries=1)
            return
        except InvalidPduState as e:
            last_error = e
            continue
    raise last_error or InvalidPduState(f"HR({address}) is not writable", None)


async def send_raw_hex(session: PlantSession, hex_str: str) -> int:
    """Write raw bytes directly to the socket, bypassing the client's framer/PDU
    layer entirely. No safety checks beyond what the device itself enforces."""
    cleaned = hex_str.strip().replace("0x", "").replace(",", " ")
    data = bytes.fromhex("".join(cleaned.split()))
    writer = session.client.writer
    writer.write(data)
    await writer.drain()
    return len(data)
