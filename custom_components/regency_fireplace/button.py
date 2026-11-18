"""Pair button: send the pairing packet while the fire is in its learn window."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FireplaceConfigEntry
from .entity import FireplaceEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FireplaceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the pair button."""
    async_add_entities([FireplacePairButton(entry, entry.runtime_data, "pair")])


class FireplacePairButton(FireplaceEntity, ButtonEntity):
    """Hold the fire's pinhole button until 3 beeps, then press this within ~10 s.

    The fire keeps a single ID: pairing locks out whatever was paired before
    (including the original handset).
    """

    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        """Send the pairing packet."""
        await self.controller.async_send_pairing(self._context)
