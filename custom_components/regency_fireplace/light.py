"""Flame and fuel bed lights."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FireplaceConfigEntry
from .entity import FireplaceEntity
from .protocol import BRIGHTNESS_MAX, FUEL_SETTINGS

PARALLEL_UPDATES = 1

FUEL_EFFECTS = [f"Setting {n}" for n in range(1, FUEL_SETTINGS + 1)]


def level_from_brightness(brightness: int) -> int:
    """Map HA brightness 1-255 onto the fire's 5 levels."""
    return max(1, min(BRIGHTNESS_MAX, math.ceil(brightness * BRIGHTNESS_MAX / 255)))


def brightness_from_level(level: int) -> int:
    """Map a fire level 1-5 onto HA brightness."""
    return round(level * 255 / BRIGHTNESS_MAX)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FireplaceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the flame and fuel bed lights."""
    controller = entry.runtime_data
    async_add_entities(
        [FlameLight(entry, controller, "flame"), FuelBedLight(entry, controller, "fuel_bed")]
    )


class FlameLight(FireplaceEntity, LightEntity):
    """The flame effect: on/off and 5 brightness levels."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def is_on(self) -> bool:
        """Return True if the flame is showing."""
        return self.controller.feature_on(self.controller.state, "flame")

    @property
    def brightness(self) -> int:
        """Return the flame brightness."""
        return brightness_from_level(self.controller.state.flame_brightness)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the flame on."""
        changes: dict[str, Any] = {}
        if ATTR_BRIGHTNESS in kwargs:
            changes["flame_brightness"] = level_from_brightness(kwargs[ATTR_BRIGHTNESS])
        await self.controller.async_feature_on("flame", self._context, **changes)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the flame off."""
        await self.controller.async_feature_off("flame", self._context)


class FuelBedLight(FireplaceEntity, LightEntity):
    """The fuel bed: 14 colour settings (as effects) and 5 brightness levels."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = FUEL_EFFECTS

    @property
    def is_on(self) -> bool:
        """Return True if the fuel bed is lit."""
        return self.controller.feature_on(self.controller.state, "fuel")

    @property
    def brightness(self) -> int:
        """Return the fuel bed brightness."""
        return brightness_from_level(self.controller.state.fuel_brightness)

    @property
    def effect(self) -> str:
        """Return the current (or remembered) colour setting."""
        setting = self.controller.state.fuel_setting or self.controller.fuel_memory
        return FUEL_EFFECTS[setting - 1]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the fuel bed on."""
        changes: dict[str, Any] = {}
        if ATTR_BRIGHTNESS in kwargs:
            changes["fuel_brightness"] = level_from_brightness(kwargs[ATTR_BRIGHTNESS])
        if ATTR_EFFECT in kwargs:
            if kwargs[ATTR_EFFECT] not in FUEL_EFFECTS:
                raise ServiceValidationError(f"Unknown fuel bed setting {kwargs[ATTR_EFFECT]!r}")
            changes["fuel_setting"] = FUEL_EFFECTS.index(kwargs[ATTR_EFFECT]) + 1
        await self.controller.async_feature_on("fuel", self._context, **changes)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fuel bed off."""
        await self.controller.async_feature_off("fuel", self._context)
