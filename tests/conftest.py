"""Fixtures: a running radio_frequency domain with a mock 433 MHz transmitter."""

from __future__ import annotations

from typing import Any

import pytest
from rf_protocols import RadioFrequencyCommand

from homeassistant.components.radio_frequency import (
    DATA_COMPONENT,
    RadioFrequencyTransmitterEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regency_fireplace.const import (
    CONF_FIRE_ID,
    CONF_TEMPERATURE_SOURCE,
    CONF_TRANSMITTER,
    DOMAIN,
)

TRANSMITTER = "radio_frequency.test_rf_transmitter"
SENSOR = "sensor.living_room_temperature"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


class MockTransmitter(RadioFrequencyTransmitterEntity):
    """Records every command instead of transmitting."""

    _attr_has_entity_name = True
    _attr_name = "Test RF transmitter"
    _attr_unique_id = "test_rf_transmitter"

    def __init__(self) -> None:
        """Initialise."""
        self.sent: list[RadioFrequencyCommand] = []
        self.fail = False

    @property
    def supported_frequency_ranges(self) -> list[tuple[int, int]]:
        """433 MHz band, like the Broadlink."""
        return [(433_050_000, 434_790_000)]

    async def async_send_command(self, command: RadioFrequencyCommand) -> None:
        """Record (or fail)."""
        if self.fail:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError("transmit failed")
        self.sent.append(command)

    def packets(self) -> list[str]:
        """Sent packets as hex strings."""
        return [c.packet.hex(" ") for c in self.sent]


@pytest.fixture
async def transmitter(hass: HomeAssistant) -> MockTransmitter:
    """A registered mock transmitter."""
    assert await async_setup_component(hass, "radio_frequency", {})
    await hass.async_block_till_done()
    entity = MockTransmitter()
    await hass.data[DATA_COMPONENT].async_add_entities([entity])
    await hass.async_block_till_done()
    return entity


def make_entry(source: str | None = None, **extra: Any) -> MockConfigEntry:
    """A config entry for fire ID A1B2."""
    data = {CONF_TRANSMITTER: TRANSMITTER, CONF_FIRE_ID: "A1B2", **extra}
    if source:
        data[CONF_TEMPERATURE_SOURCE] = source
    return MockConfigEntry(domain=DOMAIN, title="Fireplace", unique_id="A1B2", data=data)


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """Add and set up an entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
