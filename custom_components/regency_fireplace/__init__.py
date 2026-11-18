"""Regency electric fireplace (Gazco EL1039 / RF290K remote) over Radio Frequency."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_FIRE_ID, CONF_TEMPERATURE_SOURCE, CONF_TRANSMITTER
from .controller import FireplaceController

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.CLIMATE, Platform.LIGHT, Platform.SWITCH]

type FireplaceConfigEntry = ConfigEntry[FireplaceController]


def temperature_source(entry: ConfigEntry) -> str | None:
    """Return the configured temperature source; options override data."""
    return entry.options.get(CONF_TEMPERATURE_SOURCE, entry.data.get(CONF_TEMPERATURE_SOURCE)) or None


async def async_setup_entry(hass: HomeAssistant, entry: FireplaceConfigEntry) -> None:
    """Set up a fireplace from a config entry."""
    controller = FireplaceController(
        hass,
        entry.entry_id,
        transmitter=entry.data[CONF_TRANSMITTER],
        fire_id=int(entry.data[CONF_FIRE_ID], 16),
        temperature_source=temperature_source(entry),
    )
    await controller.async_setup()
    entry.runtime_data = controller
    entry.async_on_unload(controller.async_shutdown)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: FireplaceConfigEntry) -> None:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
    await entry.runtime_data.async_flush()
