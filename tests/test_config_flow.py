"""Config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.regency_fireplace.const import (
    CONF_FIRE_ID,
    CONF_TEMPERATURE_SOURCE,
    CONF_TRANSMITTER,
    DOMAIN,
)

from .conftest import SENSOR, TRANSMITTER, MockTransmitter, make_entry, setup_entry


async def test_user_flow(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """Create an entry with a temperature source; bad IDs are rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Living room", CONF_TRANSMITTER: TRANSMITTER, CONF_FIRE_ID: "xyz1"},
    )
    assert result["errors"] == {CONF_FIRE_ID: "invalid_fire_id"}

    hass.states.async_set(SENSOR, "20", {"unit_of_measurement": "°C", "device_class": "temperature"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living room",
            CONF_TRANSMITTER: TRANSMITTER,
            CONF_FIRE_ID: "a1b2",
            CONF_TEMPERATURE_SOURCE: SENSOR,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living room"
    assert result["data"] == {
        CONF_TRANSMITTER: TRANSMITTER,
        CONF_FIRE_ID: "A1B2",
        CONF_TEMPERATURE_SOURCE: SENSOR,
    }
    assert result["result"].unique_id == "A1B2"
    await hass.async_block_till_done()
    assert transmitter.sent == []  # setting up must not transmit


async def test_duplicate_id_aborts(hass: HomeAssistant, transmitter: MockTransmitter) -> None:
    """The same fire ID cannot be added twice."""
    await setup_entry(hass, make_entry())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "x", CONF_TRANSMITTER: TRANSMITTER, CONF_FIRE_ID: "A1B2"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_no_transmitters_aborts(hass: HomeAssistant) -> None:
    """Without the radio_frequency domain or transmitters, abort cleanly."""
    assert await async_setup_component(hass, "radio_frequency", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_transmitters"


async def test_options_add_and_remove_source(
    hass: HomeAssistant, transmitter: MockTransmitter
) -> None:
    """Adding a source adds the heater; clearing it removes the heater."""
    hass.states.async_set(SENSOR, "20", {"unit_of_measurement": "°C", "device_class": "temperature"})
    entry = await setup_entry(hass, make_entry())
    assert hass.states.get("climate.fireplace_heater") is None

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TEMPERATURE_SOURCE: SENSOR}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("climate.fireplace_heater") is not None

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    state = hass.states.get("climate.fireplace_heater")
    assert state is None or state.state == "unavailable"
