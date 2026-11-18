"""Entities -> packets, against a mock transmitter."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_ENTITY_ID, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import SENSOR, MockTransmitter, make_entry, setup_entry

POWER = "switch.fireplace_power"
FLAMES = "light.fireplace_flames"
FUEL = "light.fireplace_fuel_bed"
HEATER = "climate.fireplace_heater"
PAIR = "button.fireplace_pair"


def s0(tx: MockTransmitter) -> int:
    return tx.sent[-1].packet[2]


async def call(hass: HomeAssistant, domain: str, service: str, entity: str, **data) -> None:
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: entity, **data}, blocking=True
    )


async def test_entities_without_temperature_source(
    hass: HomeAssistant, transmitter: MockTransmitter
) -> None:
    """No source -> no heater; nothing is sent at setup."""
    await setup_entry(hass, make_entry())
    for entity in (POWER, FLAMES, FUEL, PAIR):
        assert hass.states.get(entity) is not None, entity
    assert hass.states.get(HEATER) is None
    assert hass.states.get(POWER).state == "off"
    assert transmitter.sent == []


async def test_power_and_flames(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """Default state matches the handset's defaults; brightness maps to 1-5."""
    await setup_entry(hass, make_entry())

    await call(hass, "switch", "turn_on", POWER)
    assert transmitter.packets()[-1] == "a1 b2 4d a3 00 00 14 14 " + _chk("a1b24da300001414")
    assert hass.states.get(FLAMES).state == "on"

    await call(hass, "light", "turn_on", FLAMES, brightness=51)
    assert s0(transmitter) == 0x49  # on, flame setting 1, brightness 1
    assert hass.states.get(FLAMES).attributes["brightness"] == 51

    await call(hass, "light", "turn_on", FLAMES, brightness=255)
    assert s0(transmitter) == 0x4D

    await call(hass, "switch", "turn_off", POWER)
    assert s0(transmitter) == 0x0D  # standby keeps flame 5
    assert hass.states.get(FLAMES).state == "off"
    assert all(c.repeat_count == 0 for c in transmitter.sent)


async def test_fuel_bed_effects_and_last_feature_off(
    hass: HomeAssistant, transmitter: MockTransmitter
) -> None:
    """Fuel bed colour/brightness; turning off the last feature goes to standby."""
    await setup_entry(hass, make_entry())
    await call(hass, "light", "turn_on", FUEL, effect="Setting 6", brightness=51)
    assert transmitter.sent[-1].packet[3] == 0x26  # brightness 1, setting 6
    assert hass.states.get(FUEL).attributes["effect"] == "Setting 6"

    # Flames + fuel on: turning the fuel bed off clears its setting only.
    await call(hass, "light", "turn_off", FUEL)
    assert transmitter.sent[-1].packet[3] == 0x20
    assert s0(transmitter) & 0x40
    # Turning it back on restores the remembered colour.
    await call(hass, "light", "turn_on", FUEL)
    assert transmitter.sent[-1].packet[3] == 0x26

    # Flames off while the fuel bed is on: flame setting cleared, power stays on.
    await call(hass, "light", "turn_off", FLAMES)
    assert s0(transmitter) == 0x45
    # Fuel bed is now the last thing showing: standby, setting kept.
    await call(hass, "light", "turn_off", FUEL)
    assert s0(transmitter) == 0x05
    assert transmitter.sent[-1].packet[3] == 0x26
    assert hass.states.get(POWER).state == "off"

    # Power on brings the fuel bed back; flames stay off as they were.
    await call(hass, "switch", "turn_on", POWER)
    assert s0(transmitter) == 0x45
    assert hass.states.get(FUEL).state == "on"
    assert hass.states.get(FLAMES).state == "off"


async def test_invalid_effect(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """Unknown effect is rejected before anything is sent."""
    await setup_entry(hass, make_entry())
    with pytest.raises(HomeAssistantError):
        await call(hass, "light", "turn_on", FUEL, effect="Setting 99")
    assert transmitter.sent == []


async def test_heater_uses_source_in_fahrenheit(
    hass: HomeAssistant, transmitter: MockTransmitter
) -> None:
    """Room temperature from a deg F sensor is sent as whole deg C."""
    hass.states.async_set(SENSOR, "70.5", {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT})
    await setup_entry(hass, make_entry(SENSOR))
    assert hass.states.get(HEATER).state == HVACMode.OFF
    assert hass.states.get(HEATER).attributes["current_temperature"] == pytest.approx(21.4, abs=0.1)

    await call(hass, "climate", "set_temperature", HEATER, temperature=22, hvac_mode=HVACMode.HEAT)
    p = transmitter.sent[-1].packet
    assert p[2] & 0x40 and p[4] == 0x04 and p[6] == 22 and p[7] == 21
    assert hass.states.get(HEATER).state == HVACMode.HEAT
    assert len(transmitter.sent) == 1  # one transmission for mode + setpoint

    await call(hass, "climate", "set_hvac_mode", HEATER, hvac_mode=HVACMode.OFF)
    assert transmitter.sent[-1].packet[4] == 0x00


async def test_climate_entity_as_source(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """A climate entity's current_temperature works as the source (system unit)."""
    hass.config.units = __import__(
        "homeassistant.util.unit_system", fromlist=["US_CUSTOMARY_SYSTEM"]
    ).US_CUSTOMARY_SYSTEM
    hass.states.async_set("climate.ecobee", "heat", {"current_temperature": 68})
    await setup_entry(hass, make_entry("climate.ecobee"))
    await call(hass, "climate", "set_hvac_mode", HEATER, hvac_mode=HVACMode.HEAT)
    assert transmitter.sent[-1].packet[7] == 20


async def test_heat_refused_without_reading(
    hass: HomeAssistant, transmitter: MockTransmitter
) -> None:
    """Never start heating against an unknown room temperature."""
    hass.states.async_set(SENSOR, "unavailable")
    await setup_entry(hass, make_entry(SENSOR))
    with pytest.raises(HomeAssistantError):
        await call(hass, "climate", "set_hvac_mode", HEATER, hvac_mode=HVACMode.HEAT)
    assert transmitter.sent == []


async def test_refresh_while_heating(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """While heating: flagged refresh every ~52 s and on temperature change."""
    hass.states.async_set(SENSOR, "20.2", {"unit_of_measurement": UnitOfTemperature.CELSIUS})
    await setup_entry(hass, make_entry(SENSOR))
    await call(hass, "climate", "set_hvac_mode", HEATER, hvac_mode=HVACMode.HEAT)
    n = len(transmitter.sent)

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=53))
    await hass.async_block_till_done()
    assert len(transmitter.sent) == n + 1
    assert s0(transmitter) & 0x80  # flagged: cannot switch the fire on/off

    # Sub-degree change: no extra send. Whole-degree change: debounced refresh.
    hass.states.async_set(SENSOR, "20.4", {"unit_of_measurement": UnitOfTemperature.CELSIUS})
    hass.states.async_set(SENSOR, "21.6", {"unit_of_measurement": UnitOfTemperature.CELSIUS})
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()
    assert transmitter.sent[-1].packet[7] == 22
    assert s0(transmitter) & 0x80


async def test_no_refresh_when_not_heating(
    hass: HomeAssistant, transmitter: MockTransmitter
) -> None:
    """Room temperature only matters while heating."""
    hass.states.async_set(SENSOR, "20", {"unit_of_measurement": UnitOfTemperature.CELSIUS})
    await setup_entry(hass, make_entry(SENSOR))
    await call(hass, "switch", "turn_on", POWER)
    n = len(transmitter.sent)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
    await hass.async_block_till_done()
    assert len(transmitter.sent) == n


async def test_stale_source_turns_heating_off(
    hass: HomeAssistant, transmitter: MockTransmitter, freezer
) -> None:
    """Source unavailable > 10 min while heating -> heating off (not before)."""
    hass.states.async_set(SENSOR, "20", {"unit_of_measurement": UnitOfTemperature.CELSIUS})
    await setup_entry(hass, make_entry(SENSOR))
    await call(hass, "climate", "set_hvac_mode", HEATER, hvac_mode=HVACMode.HEAT)
    hass.states.async_set(SENSOR, "unavailable")
    await hass.async_block_till_done()
    for minute in range(1, 13):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        if minute == 9:
            assert hass.states.get(HEATER).state == HVACMode.HEAT
            assert transmitter.sent[-1].packet[7] == 20  # keeps the last reading
    assert hass.states.get(HEATER).state == HVACMode.OFF
    assert transmitter.sent[-1].packet[4] == 0x00
    assert not s0(transmitter) & 0x80  # a real command, not a refresh


async def test_pair_button_sends_flagged(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """Pairing packet has S0 bit 7 set and does not change state."""
    await setup_entry(hass, make_entry())
    await call(hass, "button", "press", PAIR)
    assert s0(transmitter) & 0x80
    assert transmitter.sent[-1].packet[:2] == bytes.fromhex("a1b2")
    assert hass.states.get(POWER).state == "off"


async def test_failed_send_does_not_change_state(
    hass: HomeAssistant, transmitter: MockTransmitter
) -> None:
    """If the transmitter fails, the entity keeps its old state."""
    await setup_entry(hass, make_entry())
    transmitter.fail = True
    with pytest.raises(HomeAssistantError):
        await call(hass, "switch", "turn_on", POWER)
    assert hass.states.get(POWER).state == "off"


async def test_state_survives_reload(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """State is restored from storage after a reload."""
    entry = await setup_entry(hass, make_entry())
    await call(hass, "light", "turn_on", FUEL, effect="Setting 9")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(FUEL).attributes["effect"] == "Setting 9"
    assert hass.states.get(POWER).state == "on"


def _chk(hex8: str) -> str:
    from custom_components.regency_fireplace.protocol import checksum

    c = checksum(bytes.fromhex(hex8))
    return f"{c:02x} {~c & 0xFF:02x}"
