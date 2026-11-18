"""Import Home Assistant before any pytest plugin imports httpx (HA 2026.11 aliases it)."""

import homeassistant  # noqa: F401
