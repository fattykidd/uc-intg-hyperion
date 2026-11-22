# AudioControl Hyperion APR-16 Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v0.2.7 - 2026-11-22

### Fixed
- The Remote no longer stops responding ("the Hyperion is not responding") after a press or two of the volume buttons. Every change makes every entity refresh, and the sensors each asked the processor for their value while the select and the media player resent themselves in full, so one press became a burst of requests to the processor and of messages to the Remote.
- Sensors now show what the driver already knows (mute, audio mode, active input). The values that only the processor can tell (temperature, brightness, tone, signal details, host IP) are read at most once every 25 seconds, and again at once when something that affects them changes (input, tone or brightness set from the Remote, the audio signal).
- The audio mode select, Dirac slot select and media player send themselves to the Remote only when something about them changed, not on every refresh.
- A volume command is answered at once and the processor is told in the background. Presses made while a request is still on its way are merged, so the processor only ever hears the newest volume. If it refuses a change, the display goes back to its real volume.

### Tests
- New `test_responsiveness.py`: the Remote never waits on the processor, quick presses are merged, a press causes no reads of the processor, and entities are not resent unchanged. Existing volume tests wait for the background send.

## v0.2.6 - 2026-11-21

### Added
- Loudness switch (`switch.<id>.loudness`) to turn loudness compensation on and off from the Remote. It follows changes made in the processor's web UI.
- Loudness Status sensor (`sensor.<id>.loudness`), for showing the state on a Remote page. It reads On, Off, Unknown (firmware without live streams, until the switch has been used) or Not Supported.

### Changed
- The Dirac filtering and Loudness switches share one implementation. The Dirac switch behaves as before.

### Fixed
- The `Following the ... stream` debug lines never appeared in the driver log, because the stream module wasn't set to the level in `UC_LOG_LEVEL`.

### Tests
- The test processor has a loudness call and a speakers stream. New tests cover the switch and the sensor.

## v0.2.5 - 2026-11-21

### Changed
- The driver now follows the APR-16's live state streams (the same WebSockets the device's own web UI uses) instead of polling every 5 seconds. Power, volume, mute, audio mode, audio signal, input and Dirac changes reach the Remote as they happen, whether they were made on the front panel, the web UI or the Remote.
- Polling is kept as a fallback. While the streams are healthy only the 30-second full refresh runs. If a stream drops, the 5-second poll resumes, and firmware without `/ws/state` is polled as before.
- After a volume change from the Remote, the device's own volume reports are held back for 1.5 seconds, so quick presses no longer make the display jump. The display then settles on the device's value, which also corrects a change the device refused (for example past its maximum volume).

### Added
- `stream.py`: reconnects with a growing delay and replaces a connection that has gone silent for 30 seconds.

### Tests
- The fake processor can now stream state. New tests cover the stream, the client's WebSocket and the device's handling of each stream.

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