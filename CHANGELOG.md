# AudioControl Hyperion APR-16 Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v0.2.4 - 2026-11-21

### Changed
- All device HTTP traffic now goes through one shared `aiohttp` session (`client.py`) instead of opening a new session for every call.
- Sensors and buttons now share one base class each (`Apr16Sensor`, `Apr16Button`); every entity keeps its id, name and attributes. `sensor.py` and `button.py` are about 40% shorter.
- Moved the volume tables and dB/percent conversion to `volume.py`, the Dirac protocol bytes to `atlas.py`, and the input list, audio mode map and Dirac defaults to `const.py`. `device.py` is about 40% shorter.
- Volume is tracked as an integer percent and only ever sent to the device as one. The on-screen value is derived from it: percent in absolute mode, dB in relative mode.
- A failed volume change now re-reads the real volume from the device instead of leaving a wrong value on the remote.
- Select option lists (audio modes, Dirac slots) and the input list are now sent to the Remote whenever the entity state is refreshed, so a newly added entity always has them.

### Added
- Audio Bit Depth, Audio Sample Rate and Dirac Filtering Status sensors (`sensor.<id>.audio_bit_depth`, `audio_sample_rate`, `dirac_filtering`).
- The device is now polled every 5 seconds (power, volume, mute, input, audio mode), so changes made on the front panel or in the web UI show up on the remote. The remote is only updated when something changed, plus a full sensor refresh every 30 seconds. Intervals are `POLL_INTERVAL` and `FULL_REFRESH_INTERVAL` in `const.py`.
- A pytest suite (`tests/`, run with `pip install -r test-requirements.txt && pytest`). It runs the real device, client and entities against a fake APR-16 and a fake Remote, and includes a test that talks to a real local aiohttp server.
- Temperature sensor (`sensor.<id>.temperature`), read from `/v1/temperature`.
- Video Format sensor (`sensor.<id>.video_format`), read from `/v1/videoformat`.

### Tests
- Added tests for Dirac slot stepping and unknown slot names, and the test Remote now applies updates to entities like the real one.

### Removed
- The Volume +1dB / -1dB buttons. The media player's own volume controls cover them.

### Fixed
- The Dirac slot sensor and select now follow slot changes within about 5 seconds, whether made on the remote or in the device's web UI. The active slot is part of the poll, and a failed read no longer shows as slot 0.
- Dirac slots are numbered from 0, as on the device: the first slot name belongs to slot 0. Names were shown one slot off, and choosing a slot by name selected the wrong slot.
- The Dirac Filtering switch now shows the device's real filtering state (read with `GetDiracFiltering`) instead of assuming it from the active slot. The poll loop keeps it in step with changes made in the device's web UI.
- The Audio Mode sensor now shows the same friendly name as the Audio Mode select (for example "DTS Neural:X" instead of "dts-nx").
- Custom input names now reach the remote right after connecting. The device called an `update()` method that only entities have, and the error was swallowed.
- A failed sensor read no longer raises inside the sensor's own error handler (it logged `self.entity_id`, which entities don't have). The sensor now shows as unavailable instead.
- The `volume` command in relative mode no longer raises an error, and refuses positive dB values instead of jumping to 100%.
- An empty Dirac slot-name reply no longer wipes the cached slot names.
- Removed a stray `xxlimited` import and the leftover template code and TODO comments.
- The media player's current source now uses the same custom input name as its source list instead of the raw input (for example "CoreElec" rather than "HDMI 1").
- Choosing an unknown Dirac slot name is refused instead of silently switching to slot 0.
- The Dirac slot selector's "previous" command works.
- The Audio Signal and Video Signal sensors now show the device's own detail text (for example "Dolby Atmos"), instead of reading fields that the device doesn't send.

---

## v0.1.0 - 2025-12-03
### Added
- Initial template release based on ucapi-framework.
- Media player entity template with common features.
- Device communication template with connection management.
- Setup flow with manual device entry.
- mDNS device discovery template.
- Docker and Docker Compose configurations.
- Development environment with core-simulator.