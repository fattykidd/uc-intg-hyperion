"""
Dirac Live and loudness control through the APR-16's Atlas service (Connect protocol, port 80).

These calls are not part of the documented REST API. The payloads are raw
protobuf bytes captured from the device's own web UI, so this module only holds
the byte strings and the tiny parsers for the replies. The HTTP transport is in
client.py.
"""

from __future__ import annotations

import re

# RPC method names on commands.v1.AtlasService
GET_ACTIVE_SLOT = "GetDiracActiveSlot"
GET_FILTER_SLOTS = "GetDiracFilterSlots"
GET_FILTERING = "GetDiracFiltering"
SET_FILTER_SLOT = "SetDiracFilterSlot"
SET_FILTERING = "SetDiracFiltering"
SET_LOUDNESS = "SetDSP2Loudness"

# Request bodies, keyed by the slot index they select.
SLOT_PAYLOADS: dict[int, bytes] = {
    0: bytes.fromhex("1001"),
    1: bytes.fromhex("08011001"),
    2: bytes.fromhex("08021001"),
}
FILTERING_ON = bytes.fromhex("080110011801")
FILTERING_OFF = bytes.fromhex("10011801")
LOUDNESS_ON = bytes.fromhex("0801")
LOUDNESS_OFF = b""  # protobuf leaves out a zero value, so "off" is an empty request

_SLOT_NAME_PATTERN = re.compile(rb"\x0b([^\x1a]+)\x1a")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def browser_headers(origin: str) -> dict[str, str]:
    """Extra headers the device expects on the slot-name request (mimics its web UI)."""
    return {
        "Accept": "*/*",
        "Origin": origin,
        "Referer": f"{origin}/",
        "User-Agent": "UnfoldedCircle-HyperionIntegration/1.0",
    }


def parse_active_slot(body: bytes) -> int:
    """Read the active slot from a GetDiracActiveSlot reply. An empty reply means slot 0."""
    if len(body) >= 2 and body[0] == 0x08:
        return body[1]
    return 0


def parse_filtering(body: bytes) -> bool:
    """
    Read whether Dirac filtering is on from a GetDiracFiltering reply.

    The reply is field 1 as a boolean (``08 01`` for on, followed by constant fields). Protobuf leaves
    out zero values, so an empty reply means off.
    """
    return len(body) >= 2 and body[0] == 0x08 and body[1] != 0


def parse_slot_names(body: bytes) -> dict[int, str]:
    """Pull the user-defined slot names out of a GetDiracFilterSlots reply. The first name is slot 0."""
    names: list[str] = []
    for raw in _SLOT_NAME_PATTERN.findall(body):
        cleaned = _CONTROL_CHARS.sub("", raw.decode("utf-8", errors="ignore").strip())
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return dict(enumerate(names))
