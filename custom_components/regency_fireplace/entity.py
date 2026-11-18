"""Base entity for the Regency Fireplace integration."""

from __future__ import annotations

from homeassistant.components.radio_frequency import (
    RadioFrequencyTransmitterConsumerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .controller import FireplaceController


class FireplaceEntity(RadioFrequencyTransmitterConsumerEntity):
    """An entity that reflects (and changes) the shared fireplace state.

    Availability follows the RF transmitter. RF is one-way, so state is
    whatever was last sent successfully.
    """

    _attr_has_entity_name = True
    _attr_assumed_state = True

    def __init__(self, entry: ConfigEntry, controller: FireplaceController, key: str) -> None:
        """Initialise the entity."""
        self.controller = controller
        self._rf_transmitter_entity_id = controller.transmitter
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Regency",
            model="Electric fireplace (EL1039 remote)",
            serial_number=f"RF ID {controller.fire_id:04X}",
        )

    async def async_added_to_hass(self) -> None:
        """Follow controller updates."""
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))
