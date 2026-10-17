![Screenshot 1](assets/Wallpaper2.png)
# Unfolded Circle Remote Driver for the AudioControl Hyperion APR-16  (Pre-Release)

[![GitHub Release](https://img.shields.io/github/v/release/Fattykidd/uc-intg-hyperion?style=flat-square&color=blue)](https://github.com/Fattykidd/uc-intg-hyperion/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

An integration driver for the **Unfolded Circle Remote 3** and **Remote Two**, written in Python using the official `ucapi-framework`. This driver provides full local network control, real-time diagnostic polling, and system management for the [Hyperion Apr-16](https://www.avproglobal.com/products/acp-hype-apr-16) Immersive Sound Pre-Amp Processor.

---

## Features

- **Full Native Media Player Entity**:
  - Discrete power control (`ON`, `OFF`, `TOGGLE`).
  - Master volume control with smooth stepping and discrete level setting.
  - Master mute toggling.
  - Active input source switching (`HDMI 1–7`, `eARC`, `Coaxial 1–2`, `Optical 1–2`, `Analog 1–2`, `Dante`).
  - Active sound mode and upmixer selection (`Direct`, `Stereo`, `All Channel Stereo`, `Dolby Surround`, `DTS Neural:X`, `Native / Auto`).
  - Real-time metadata mapping for incoming stream details (format, sample rate, video mode).

- **Granular System Controls**:
  - **Volume Safety Limits**: Configurable power-on default volume and maximum allowable volume limit to protect speakers.
  - **Channel Calibration**: Real-time individual channel level trim controls (-20.0 dB to +10.0 dB in 0.5 dB steps).
  - **Hardware Triggers**: Independent control of the 12V / 5V trigger output and voltage mode switching (12V standard vs. 5V TTL).
  - **HDMI & EDID Diagnostics**: Global EDID advertisement toggling, input-specific EDID mode status monitoring, and a dedicated **HDMI Handshake Reset (HPD Pulse)** macro to resolve HDMI handshaking lockups without hard power cycles.
  - **System Maintenance**: Graceful system reboot action button and live firmware/build metadata monitoring.

- **Diagnostic Telemetry**:
  - Live incoming audio stream metrics: Codec/Format, Bit Depth, and Sample Rate (Hz).
  - Live video stream format and resolution breakdown.
  - Overall system health status and network management interface IP monitoring.

---

## Deployment Options

### Option 1: Docker Container (Recommended)

The driver is continuously compiled into multi-architecture Docker container images targeting `linux/amd64` and `linux/arm64` via GitHub Actions and hosted on GitHub Container Registry (`ghcr.io`).

#### Using Docker Run
```
docker run -d \
  --name uc-hyperion-apr16 \
  --restart unless-stopped \
  --net host \
  ghcr.io/fattykidd/uc-intg-hyperion:latest
  ```

#### Using Docker Compose
```
uc-intg-hyperion:
    image: ghcr.io/fattykidd/uc-intg-hyperion:latest
    container_name: uc-intg-hyperion
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./hyperion/data:/data  # Persistent configuration storage
    environment:
      - UC_CONFIG_HOME=/data
      - UC_INTEGRATION_INTERFACE=0.0.0.0
      - UC_INTEGRATION_HTTP_PORT=9090
      - UC_DISABLE_MDNS_PUBLISH=false
      - PYTHONPATH=/app

```

## Integration Setup (Unfolded Circle Remote)


1. Open the Unfolded Circle Web Configurator or Remote UI.

2. Navigate to Integrations -> Add Integration -> Custom Driver.

3. Select Websocket / Network Integration.

4. Enter the IP address and port (9090) where the driver container or Python process is running.

5. In the setup prompt, enter the local IPv4 address or hostname of your AudioControl Hyperion APR-16 processor.

6. The Remote will discover and register all entities automatically (Media Player, Selects, Numbers, Switches, Sensors, and Buttons).

## Acknowledgments & Attribution

* **[Jack Powell](https://github.com/JackJPowell)** — For creating and maintaining the foundational Python driver framework ([`ucapi-framework`](https://github.com/JackJPowell/ucapi-framework)) and integration template ([`uc-intg-template`](https://github.com/JackJPowell/uc-intg-template)).
* **[Unfolded Circle](https://unfoldedcircle.com/)** — For creating an exceptional smart remote ecosystem and flexible open API architecture.
* **[AudioControl](https://www.audiocontrol.com/)** — For engineering high-end home theater processing hardware.
* **The Open-Source Community** — To all the independent developers and hobbyists whose dedication fuels custom integrations and ecosystem expansion.
* **Gemini** — For collaborative architecture, driver design, and implementation support throughout development.