"""Config flow for the Regency Fireplace integration."""

from __future__ import annotations

import random
import re
from typing import Any

import probatio

from homeassistant.components.radio_frequency import ModulationType, async_get_transmitters
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, selector

from .const import CONF_FIRE_ID, CONF_TEMPERATURE_SOURCE, CONF_TRANSMITTER, DOMAIN
from .protocol import FREQUENCY

_FIRE_ID_RE = re.compile(r"^[0-9A-Fa-f]{4}$")

TEMPERATURE_SOURCE_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        filter=[
            selector.EntityFilterSelectorConfig(domain="sensor", device_class="temperature"),
            selector.EntityFilterSelectorConfig(domain="climate"),
        ]
    )
)


def _random_fire_id() -> str:
    """Return a random ID, avoiding all-zeros/all-ones."""
    return f"{random.randint(0x0001, 0xFFFE):04X}"


class RegencyFireplaceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one fireplace."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose transmitter, ID and (optionally) a temperature source."""
        try:
            transmitters = async_get_transmitters(self.hass, FREQUENCY, ModulationType.OOK)
        except HomeAssistantError:
            return self.async_abort(reason="no_transmitters")
        if not transmitters:
            return self.async_abort(reason="no_compatible_transmitters")

        errors: dict[str, str] = {}
        if user_input is not None:
            fire_id = user_input[CONF_FIRE_ID].strip().upper()
            if not _FIRE_ID_RE.match(fire_id) or fire_id in ("0000", "FFFF"):
                errors[CONF_FIRE_ID] = "invalid_fire_id"
            else:
                await self.async_set_unique_id(fire_id)
                self._abort_if_unique_id_configured()
                transmitter = er.async_get(self.hass).async_get(user_input[CONF_TRANSMITTER])
                assert transmitter is not None
                data = {
                    CONF_TRANSMITTER: transmitter.entity_id,
                    CONF_FIRE_ID: fire_id,
                }
                if source := user_input.get(CONF_TEMPERATURE_SOURCE):
                    data[CONF_TEMPERATURE_SOURCE] = source
                return self.async_create_entry(title=user_input[CONF_NAME], data=data)

        schema = probatio.Schema(
            {
                probatio.Required(CONF_NAME, default="Fireplace"): str,
                probatio.Required(CONF_TRANSMITTER): selector.EntitySelector(
                    selector.EntitySelectorConfig(include_entities=transmitters)
                ),
                probatio.Required(CONF_FIRE_ID, default=_random_fire_id()): str,
                probatio.Optional(CONF_TEMPERATURE_SOURCE): TEMPERATURE_SOURCE_SELECTOR,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RegencyFireplaceOptionsFlow:
        """Return the options flow."""
        return RegencyFireplaceOptionsFlow()


class RegencyFireplaceOptionsFlow(OptionsFlowWithReload):
    """Change (or remove) the temperature source."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the temperature source option."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_TEMPERATURE_SOURCE: user_input.get(CONF_TEMPERATURE_SOURCE)}
            )
        current = self.config_entry.options.get(
            CONF_TEMPERATURE_SOURCE, self.config_entry.data.get(CONF_TEMPERATURE_SOURCE)
        )
        schema = probatio.Schema(
            {probatio.Optional(CONF_TEMPERATURE_SOURCE): TEMPERATURE_SOURCE_SELECTOR}
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_TEMPERATURE_SOURCE: current} if current else {}
            ),
        )
