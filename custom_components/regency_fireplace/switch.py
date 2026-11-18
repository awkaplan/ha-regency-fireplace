"""Power switch: the handset's POWER button (standby keeps every setting)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FireplaceConfigEntry
from .entity import FireplaceEntity
from .protocol import FireplaceState

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FireplaceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the power switch."""
    async_add_entities([FireplacePower(entry, entry.runtime_data, "power")])


class FireplacePower(FireplaceEntity, SwitchEntity):
    """Fire on / standby."""

    @property
    def is_on(self) -> bool:
        """Return True when the fire is out of standby."""
        return self.controller.state.power

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Leave standby, restoring the remembered settings."""

        def change(state: FireplaceState) -> FireplaceState:
            new = state.evolve(power=True)
            nothing_on = not any(
                self.controller.feature_on(new, f) for f in ("flame", "fuel", "heat")
            )
            # With every feature off, "on" would look like nothing happened.
            return new.evolve(flame=True) if nothing_on else new

        await self.controller.async_update(change, context=self._context)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Go to standby."""
        await self.controller.async_update(
            lambda s: s.evolve(power=False), context=self._context
        )
