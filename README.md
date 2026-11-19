<img src="custom_components/regency_fireplace/brand/icon.png" alt="Flame icon" width="96" align="right">

# Regency Electric Fireplace for Home Assistant

Control a Regency electric fireplace that uses the **EL1039** remote (keypad board `RF290K`) from Home Assistant: power, flames, fuel bed and the thermostatic heater.

It's a consumer of Home Assistant's built-in [Radio Frequency](https://www.home-assistant.io/integrations/radio_frequency/) building block. It needs **no extra hardware beyond a 433 MHz transmitter** that Home Assistant already supports, such as a **Broadlink RM4 Pro**. It doesn't depend on any particular transmitter.

> This project isn't affiliated with Regency, Gazco or the remote's manufacturer. It was reverse engineered from radio captures. The fire's heater is a real heater: read [Heater safety](#heater-safety) before turning it on from automations.

## Requirements

- Home Assistant **2026.11** or newer.
- A radio frequency transmitter entity that supports **433.92 MHz OOK**. The Broadlink integration provides one for the RM4 Pro, and ESPHome devices with a CC1101 also work.
- A fire paired to (or pairable with) an EL1039 remote. It has been tested with a Regency 223-088. Other fires sold with the EL1039 / RF290K remote should work; please [open an issue](https://github.com/awkaplan/ha-regency-fireplace/issues) with your model either way.

## Installation

### Marketplace / HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=awkaplan&repository=ha-regency-fireplace&category=integration)

Or add `https://github.com/awkaplan/ha-regency-fireplace` as a custom repository of type **Integration**, then download **Regency Electric Fireplace**.

### Manual

Copy `custom_components/regency_fireplace` into your Home Assistant `config/custom_components/` folder, then restart.

## Setup

[![Open your Home Assistant instance and start setting up Regency Electric Fireplace.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=regency_fireplace)

The setup form asks for:

| Field | Notes |
|---|---|
| Name | Used for the device and entity names. |
| Radio frequency transmitter | Any transmitter entity that supports 433.92 MHz OOK. |
| Fire ID | 4 hex digits. A random ID is suggested. To keep using your original remote alongside Home Assistant, enter **the remote's own ID** instead (see below). |
| Room temperature source | Optional. A temperature sensor or a climate entity in the same room. **The heater entity only exists when this is set.** You can add, change or remove it later under *Configure*. |

### Pairing a new ID

The fire obeys **one ID only**. Pairing a new ID locks out whatever was paired before, including the original remote.

1. Hold the **pinhole reset button** on the fire's right-hand control panel with a pen until the fire beeps **3 times**.
2. Within 10 seconds, press the device's **Pair** button in Home Assistant.
3. Turn on **Power**. The fire should respond.

To give control back to the original remote later, repeat step 1, then press **POWER** on the remote.

### Sharing control with the original remote

Every packet carries the fire's complete state, so Home Assistant can use the remote's own ID without pairing anything. Read the ID with an SDR (for example `rtl_433 -f 433.92M -s 250k -A`, then press a button on the remote) and enter it as the Fire ID.

Because radio is one-way, Home Assistant only knows what it last sent. A button press on the remote changes the fire without Home Assistant seeing it, and the remote's periodic re-broadcasts can override Home Assistant's settings.

## Entities

| Entity | What it does |
|---|---|
| `switch.<name>_power` | On / standby, like the remote's POWER button. Standby keeps every setting. |
| `light.<name>_flames` | Flame effect on/off, brightness in 5 steps. |
| `light.<name>_fuel_bed` | Fuel bed on/off, brightness in 5 steps, colour as an effect ("Setting 1" to "Setting 14"). |
| `climate.<name>_heater` | Off / Heat with a setpoint in whole °C (5–40, the remote's range). Only present with a temperature source. |
| `button.<name>_pair` | Sends the pairing packet (configuration entity). |

Turning on a light or the heater also takes the fire out of standby. Turning off the last thing that's on puts the fire into standby and remembers that setting, so **Power** brings it back.

## Heater safety

The fire runs its own thermostat from the room temperature in the last packet it received. This integration:

- Refuses to start heating until the temperature source has a reading.
- Re-sends the current room temperature every ~52 s while heating, as the remote does, and soon after a whole-degree change.
- Turns heating off if the temperature source stays unavailable for 10 minutes.

If Home Assistant itself stops while heating, the fire keeps working from the last temperature it was sent. Its own overheat cut-out still applies. Follow the fireplace manual's safety instructions; in particular, don't leave it heating unattended.

## Limitations

- **No timer.** Use a Home Assistant automation instead.
- **Fuel bed colours have no names.** The 14 colour settings are listed by number.
- **State is assumed** (`assumed_state`), since radio is one-way.

## How it works

See [docs/protocol.md](docs/protocol.md) for the radio protocol, packet layout and pairing behaviour.

## Development

Run the tests (Python 3.14):

```bash
python -m venv .venv && . .venv/bin/activate
script/setup_test_env.sh
python -m pytest
```
