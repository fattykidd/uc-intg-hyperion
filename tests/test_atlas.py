"""Tests for the Dirac (Atlas) protobuf helpers."""

import atlas


def test_active_slot_parsing():
    assert atlas.parse_active_slot(b"") == 0
    assert atlas.parse_active_slot(b"\x08\x02") == 2
    assert atlas.parse_active_slot(b"\x10\x01") == 0  # unexpected field: fall back to slot 0


def test_slot_name_parsing_strips_control_characters_and_duplicates():
    body = b"\x0bMovie Night\x1a\x00\x0bMusic\x1a\x0bMovie Night\x1a"
    assert atlas.parse_slot_names(body) == {1: "Movie Night", 2: "Music"}


def test_slot_name_parsing_of_garbage_gives_nothing():
    assert atlas.parse_slot_names(b"") == {}
    assert atlas.parse_slot_names(b"\x00\x01\x02") == {}


def test_payloads_match_the_captured_bytes():
    assert atlas.SLOT_PAYLOADS[1] == b"\x08\x01\x10\x01"
    assert atlas.FILTERING_ON == b"\x08\x01\x10\x01\x18\x01"
    assert atlas.FILTERING_OFF == b"\x10\x01\x18\x01"
