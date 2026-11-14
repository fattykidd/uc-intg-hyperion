"""Tests for the Dirac (Atlas) protobuf helpers."""

import atlas


def test_active_slot_parsing():
    assert atlas.parse_active_slot(b"") == 0
    assert atlas.parse_active_slot(b"\x08\x02") == 2
    assert atlas.parse_active_slot(b"\x10\x01") == 0  # unexpected field: fall back to slot 0


def test_slot_name_parsing_strips_control_characters_and_duplicates():
    body = b"\x0bMovie Night\x1a\x00\x0bMusic\x1a\x0bMovie Night\x1a"
    assert atlas.parse_slot_names(body) == {0: "Movie Night", 1: "Music"}


def test_slot_name_parsing_of_garbage_gives_nothing():
    assert atlas.parse_slot_names(b"") == {}
    assert atlas.parse_slot_names(b"\x00\x01\x02") == {}


def test_payloads_match_the_captured_bytes():
    assert atlas.SLOT_PAYLOADS[1] == b"\x08\x01\x10\x01"
    assert atlas.FILTERING_ON == b"\x08\x01\x10\x01\x18\x01"
    assert atlas.FILTERING_OFF == b"\x10\x01\x18\x01"


def test_filtering_replies_captured_from_the_device():
    assert atlas.parse_filtering(bytes.fromhex("080110011801")) is True  # GetDiracFiltering, filtering on
    assert atlas.parse_filtering(b"") is False  # filtering off: every field is zero and left out
    assert atlas.parse_filtering(bytes.fromhex("0801")) is True  # GetDiracEnabled, on
    assert atlas.parse_filtering(bytes.fromhex("0800")) is False
    assert atlas.parse_filtering(bytes.fromhex("1001")) is False  # some other field first: not on


def test_slot_names_from_a_captured_reply():
    entry = lambda slot, name: (b"\x08" + bytes([slot]) if slot else b"") + b"\x12" + bytes([len(name)]) + name + b"\x1a\x04abcd"
    body = b"".join(b"\x0a" + bytes([len(e)]) + e for e in (entry(0, b"4dB current"), entry(1, b"2dB current"), entry(2, b"6dB current")))
    assert atlas.parse_slot_names(body) == {0: "4dB current", 1: "2dB current", 2: "6dB current"}
