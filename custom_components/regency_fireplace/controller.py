"""Shared state and transmission for one fireplace."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.radio_frequency import async_send_command
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    DOMAIN,
    REFRESH_INTERVAL,
    STORAGE_VERSION,
    TEMPERATURE_DEBOUNCE,
)
from .protocol import El1039Command, FireplaceState

_LOGGER = logging.getLogger(__name__)

# If the temperature source stays unavailable this long while heating, turn
# heating off rather than let the fire's thermostat run on a stale reading.
STALE_SOURCE_LIMIT = timedelta(minutes=10)
ROOM_TEMP_RANGE = (0, 60)


class FireplaceController:
    """Owns the fire's state and is the only thing that transmits to it."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        transmitter: str,
        fire_id: int,
        temperature_source: str | None,
    ) -> None:
        """Initialise the controller."""
        self.hass = hass
        self.transmitter = transmitter
        self.fire_id = fire_id
        self.temperature_source = temperature_source
        self.state = FireplaceState()
        self.fuel_memory = self.state.fuel_setting  # colour to restore when turned back on
        self.source_temperature: float | None = None  # deg C, unrounded
        self._source_lost_at: datetime | None = None
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self._unsubs: list[CALLBACK_TYPE] = []
        self._debounce: CALLBACK_TYPE | None = None

    @property
    def has_temperature_source(self) -> bool:
        """Return True when heating can be offered."""
        return self.temperature_source is not None

    # ---------------------------------------------------------------- lifecycle
    async def async_setup(self) -> None:
        """Restore state and start tracking."""
        if (data := await self._store.async_load()) is not None:
            try:
                self.state = FireplaceState.from_dict(data.get("state", {}))
            except (TypeError, ValueError) as err:
                _LOGGER.warning("Ignoring stored fireplace state: %s", err)
            self.fuel_memory = data.get("fuel_memory", self.fuel_memory) or 3
        if not self.has_temperature_source and self.state.heat:
            self.state = self.state.evolve(heat=False)

        if self.temperature_source is not None:
            self._read_source()
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, [self.temperature_source], self._source_changed
                )
            )
            self._unsubs.append(
                async_track_time_interval(self.hass, self._async_refresh_tick, REFRESH_INTERVAL)
            )

    @callback
    def async_shutdown(self) -> None:
        """Stop tracking."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._debounce is not None:
            self._debounce()
            self._debounce = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Register an entity update callback."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # ---------------------------------------------------------------- sending
    async def _async_transmit(
        self, state: FireplaceState, *, flag: bool, context: Context | None
    ) -> None:
        command = El1039Command(self.fire_id, state, flag=flag)
        _LOGGER.debug("Sending %r", command)
        await async_send_command(self.hass, self.transmitter, command, context=context)

    async def async_update(
        self,
        change: Callable[[FireplaceState], FireplaceState],
        *,
        context: Context | None = None,
    ) -> None:
        """Apply a change and send the resulting full state.

        The change is computed under the lock from the latest state, so
        concurrent service calls (e.g. a dragged slider) cannot undo each other.
        State is committed only once the transmitter accepted the burst.
        """
        async with self._lock:
            new = change(self.state)
            if new.heat and not self.has_temperature_source:
                new = new.evolve(heat=False)
            starts_heating = self.feature_on(new, "heat") and not self.feature_on(
                self.state, "heat"
            )
            if starts_heating and self.source_temperature is None:
                raise HomeAssistantError(
                    f"Not heating: temperature source {self.temperature_source} has no reading"
                )
            new = new.evolve(room_temperature=self._room_byte())
            await self._async_transmit(new, flag=False, context=context)
            if new.fuel_setting:
                self.fuel_memory = new.fuel_setting
            self.state = new
            self._save()
        self._notify()

    # ---------------------------------------------------------------- features
    # The fire has one power bit (POWER on the handset: standby keeps every
    # setting) plus three features. A feature shows only while power is on.
    @staticmethod
    def feature_on(state: FireplaceState, feature: str) -> bool:
        """Return True if the feature is visibly on."""
        enabled = {
            "flame": state.flame,
            "fuel": state.fuel_setting > 0,
            "heat": state.heat,
        }[feature]
        return state.power and enabled

    async def async_feature_on(
        self, feature: str, context: Context | None = None, **changes: Any
    ) -> None:
        """Turn a feature on (and the fire out of standby), with optional changes."""

        def change(state: FireplaceState) -> FireplaceState:
            enable: dict[str, Any] = {
                "flame": {"flame": True},
                "fuel": {"fuel_setting": state.fuel_setting or self.fuel_memory},
                "heat": {"heat": True},
            }[feature]
            return state.evolve(power=True, **{**enable, **changes})

        await self.async_update(change, context=context)

    async def async_feature_off(self, feature: str, context: Context | None = None) -> None:
        """Turn a feature off; if it was the last one showing, go to standby instead.

        Going to standby keeps the feature's setting, so POWER brings it back,
        exactly like the handset.
        """

        def change(state: FireplaceState) -> FireplaceState:
            others = [f for f in ("flame", "fuel", "heat") if f != feature]
            if not any(self.feature_on(state, f) for f in others):
                return state.evolve(power=False)
            disable: dict[str, Any] = {
                "flame": {"flame": False},
                "fuel": {"fuel_setting": 0},
                "heat": {"heat": False},
            }[feature]
            return state.evolve(**disable)

        await self.async_update(change, context=context)

    async def async_send_pairing(self, context: Context | None = None) -> None:
        """Send the current state flagged, which a fire in its learn window pairs to."""
        async with self._lock:
            await self._async_transmit(
                self.state.evolve(room_temperature=self._room_byte()), flag=True, context=context
            )

    async def _async_refresh(self) -> None:
        """Re-send the state with a fresh room temperature.

        Flagged like the handset's own re-broadcasts, so it can never switch the
        fire on or off (e.g. after someone turned it off at the fire itself).
        """
        async with self._lock:
            state = self.state.evolve(room_temperature=self._room_byte())
            try:
                await self._async_transmit(state, flag=True, context=None)
            except HomeAssistantError as err:
                _LOGGER.warning("Fireplace refresh failed: %s", err)
                return
            self.state = state
            self._save()
        self._notify()

    # ---------------------------------------------------------------- temperature
    def _room_byte(self) -> int:
        if self.source_temperature is None:
            return self.state.room_temperature
        lo, hi = ROOM_TEMP_RANGE
        return max(lo, min(hi, round(self.source_temperature)))

    def _read_source(self, now: datetime | None = None) -> None:
        """Update source_temperature from the configured entity."""
        assert self.temperature_source is not None
        value = _celsius_from_state(self.hass, self.temperature_source)
        if value is None:
            if self._source_lost_at is None:
                self._source_lost_at = now or dt_util.utcnow()
                _LOGGER.warning(
                    "Temperature source %s has no reading; keeping the last value",
                    self.temperature_source,
                )
            return
        self._source_lost_at = None
        self.source_temperature = value

    @callback
    def _source_changed(self, event: Event[EventStateChangedData]) -> None:
        before = self._room_byte()
        self._read_source()
        self._notify()
        if self.state.power and self.state.heat and self._room_byte() != before:
            if self._debounce is not None:
                self._debounce()
            self._debounce = async_call_later(
                self.hass, TEMPERATURE_DEBOUNCE, self._async_debounced_refresh
            )

    async def _async_debounced_refresh(self, _now: datetime) -> None:
        self._debounce = None
        await self._async_refresh()

    async def _async_refresh_tick(self, now: datetime) -> None:
        if not (self.state.power and self.state.heat):
            return
        self._read_source(now)
        if (
            self._source_lost_at is not None
            and now - self._source_lost_at > STALE_SOURCE_LIMIT
        ):
            _LOGGER.warning(
                "Temperature source %s unavailable for over %s; turning heating off",
                self.temperature_source,
                STALE_SOURCE_LIMIT,
            )
            try:
                await self.async_update(lambda s: s.evolve(heat=False))
            except HomeAssistantError as err:
                _LOGGER.warning("Could not turn heating off: %s", err)
            return
        await self._async_refresh()

    # ---------------------------------------------------------------- storage
    def _data(self) -> dict[str, Any]:
        return {"state": self.state.as_dict(), "fuel_memory": self.fuel_memory}

    def _save(self) -> None:
        self._store.async_delay_save(self._data, 1)

    async def async_flush(self) -> None:
        """Write state now (on unload/reload; HA stop is handled by the Store)."""
        await self._store.async_save(self._data())


def _celsius_from_state(hass: HomeAssistant, entity_id: str) -> float | None:
    """Read a temperature in deg C from a sensor or a climate entity."""
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    system_unit = hass.config.units.temperature_unit
    if state.domain == "climate":
        raw = state.attributes.get("current_temperature")
        unit = system_unit
    else:
        raw = state.state
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or system_unit
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if unit not in TemperatureConverter.VALID_UNITS:
        return None
    return TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)
