"""Heater, offered only when a temperature source is configured.

The fire runs its thermostat from the room temperature carried in every
packet. Without a real source it would heat against a fixed number, so the
heater is not exposed at all in that case.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FireplaceConfigEntry
from .entity import FireplaceEntity
from .protocol import SETPOINT_MAX, SETPOINT_MIN

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FireplaceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the heater if there is a temperature source."""
    controller = entry.runtime_data
    if controller.has_temperature_source:
        async_add_entities([FireplaceHeater(entry, controller, "heater")])


class FireplaceHeater(FireplaceEntity, ClimateEntity):
    """Thermostatic heater: off / heat with a whole-degree Celsius setpoint."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_precision = PRECISION_TENTHS  # source reading; the setpoint step stays 1
    _attr_min_temp = SETPOINT_MIN
    _attr_max_temp = SETPOINT_MAX

    @property
    def hvac_mode(self) -> HVACMode:
        """Return heat while heating is enabled and the fire is on."""
        on = self.controller.feature_on(self.controller.state, "heat")
        return HVACMode.HEAT if on else HVACMode.OFF

    @property
    def target_temperature(self) -> float:
        """Return the setpoint."""
        return self.controller.state.setpoint

    @property
    def current_temperature(self) -> float | None:
        """Return the temperature source's reading."""
        return self.controller.source_temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose what the fire was last told the room temperature is."""
        return {"sent_room_temperature": self.controller.state.room_temperature}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn heating on or off."""
        if hvac_mode == HVACMode.HEAT:
            await self.controller.async_feature_on("heat", self._context)
        else:
            await self.controller.async_feature_off("heat", self._context)

    async def async_turn_on(self) -> None:
        """Turn heating on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn heating off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the setpoint (and optionally the mode) in one transmission."""
        changes: dict[str, Any] = {}
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            changes["setpoint"] = max(SETPOINT_MIN, min(SETPOINT_MAX, round(temperature)))
        mode = kwargs.get(ATTR_HVAC_MODE)
        if mode == HVACMode.HEAT:
            await self.controller.async_feature_on("heat", self._context, **changes)
            return
        if changes:
            await self.controller.async_update(
                lambda s: s.evolve(**changes), context=self._context
            )
        if mode == HVACMode.OFF:
            await self.controller.async_feature_off("heat", self._context)
