"""Regency / Gazco EL1039 (RF290K) 433.92 MHz OOK protocol.

Reverse engineered from an EL1039 handset and a Regency 223-088 fire with an
RTL-SDR; see docs/protocol.md in the repository for how each field was found.

Every packet carries the *complete* fire state, so a command is "here is how
the fire should be", never "press this button".

    [ID_hi][ID_lo][S0][S1][S2][S3][S4][S5][CHK][~CHK]

    S0  bit 7    flag: required on the pairing packet; flagged packets do not
                 switch the fire on or off (the handset sets it on its periodic
                 re-broadcasts)
        bit 6    power (on / standby)
        bits 5-3 flame setting (1 = flame on, 0 = flame off)
        bits 2-0 flame brightness 1-5
    S1  bits 7-5 fuel bed brightness 1-5
        bits 4-0 fuel bed setting (0 = off, 1-14 = colour settings)
    S2  bits 7-4 timer step (not used here)
        bit 2    heating enabled
    S3  0x00
    S4  heating setpoint, whole deg C
    S5  room temperature, whole deg C (the fire runs the thermostat from this)
    CHK (sum of the 8 bytes before it + 0x55) & 0xFF, then its complement
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from rf_protocols import ModulationType, RadioFrequencyCommand

FREQUENCY = 433_920_000

# Microseconds, measured from the handset (captures/baseline).
_PRE_MARK, _PRE_SPACE, _PRE_COUNT = 336, 664, 10
_ZERO_MARK, _ONE_MARK, _SPACE = 140, 540, 564
_TRAILER_MARK, _PACKET_GAP = 20_030, 10_080
PACKETS_PER_BURST = 3

BRIGHTNESS_MIN, BRIGHTNESS_MAX = 1, 5
FUEL_SETTINGS = 14  # colour settings 1..14; 0 is off
SETPOINT_MIN, SETPOINT_MAX = 15, 30  # deg C; observed range 19-23, wider is unverified
ROOM_TEMP_DEFAULT = 20  # deg C, sent while no temperature source is configured


def checksum(data: bytes) -> int:
    """Return the EL1039 checksum byte."""
    return (sum(data) + 0x55) & 0xFF


@dataclass(frozen=True, slots=True)
class FireplaceState:
    """Complete fire state, as carried by one packet."""

    power: bool = False
    flame: bool = True
    flame_brightness: int = 5
    fuel_setting: int = 3
    fuel_brightness: int = 5
    heat: bool = False
    setpoint: int = 20
    room_temperature: int = ROOM_TEMP_DEFAULT

    def __post_init__(self) -> None:
        """Validate ranges so a bad value can never reach the fire."""
        for name in ("flame_brightness", "fuel_brightness"):
            value = getattr(self, name)
            if not BRIGHTNESS_MIN <= value <= BRIGHTNESS_MAX:
                raise ValueError(f"{name} must be {BRIGHTNESS_MIN}-{BRIGHTNESS_MAX}, got {value}")
        if not 0 <= self.fuel_setting <= FUEL_SETTINGS:
            raise ValueError(f"fuel_setting must be 0-{FUEL_SETTINGS}, got {self.fuel_setting}")
        if not SETPOINT_MIN <= self.setpoint <= SETPOINT_MAX:
            raise ValueError(f"setpoint must be {SETPOINT_MIN}-{SETPOINT_MAX}, got {self.setpoint}")
        if not 0 <= self.room_temperature <= 0xFF:
            raise ValueError(f"room_temperature must fit in a byte, got {self.room_temperature}")

    def evolve(self, **changes: Any) -> FireplaceState:
        """Return a copy with some fields changed."""
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FireplaceState:
        """Build from a stored dict, ignoring unknown keys."""
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})

    def state_bytes(self, flag: bool = False) -> bytes:
        """Return S0..S5."""
        s0 = (
            (0x80 if flag else 0)
            | (0x40 if self.power else 0)
            | ((1 if self.flame else 0) << 3)
            | self.flame_brightness
        )
        s1 = self.fuel_brightness << 5 | self.fuel_setting
        s2 = 0x04 if self.heat else 0x00
        return bytes([s0, s1, s2, 0x00, self.setpoint, self.room_temperature])


def build_packet(fire_id: int, state: FireplaceState, flag: bool = False) -> bytes:
    """Return the 10-byte packet for this ID and state."""
    if not 0 <= fire_id <= 0xFFFF:
        raise ValueError(f"fire_id must be 16 bits, got {fire_id:#x}")
    data = fire_id.to_bytes(2, "big") + state.state_bytes(flag)
    chk = checksum(data)
    return data + bytes([chk, ~chk & 0xFF])


def packet_timings(packet: bytes) -> list[int]:
    """One packet as signed timings: marks positive, spaces negative."""
    out: list[int] = []
    for _ in range(_PRE_COUNT):
        out += [_PRE_MARK, -_PRE_SPACE]
    for byte in packet:
        for bit in range(7, -1, -1):
            out += [_ONE_MARK if byte >> bit & 1 else _ZERO_MARK, -_SPACE]
    out += [_TRAILER_MARK, -_PACKET_GAP]
    return out


class El1039Command(RadioFrequencyCommand):
    """A full burst: wake-up carrier, then three identical packets.

    The burst is built explicitly with repeat_count 0: the fire rejected an
    RM4 Pro's own hardware repeat (it leaves ~17 ms between packets where the
    handset leaves 10 ms).
    """

    def __init__(self, fire_id: int, state: FireplaceState, *, flag: bool = False) -> None:
        """Initialise the command."""
        super().__init__(frequency=FREQUENCY, modulation=ModulationType.OOK, repeat_count=0)
        self.fire_id = fire_id
        self.state = state
        self.flag = flag
        self.packet = build_packet(fire_id, state, flag)

    def get_raw_timings(self) -> list[int]:
        """Return the burst as signed microsecond timings."""
        out = [_TRAILER_MARK, -_PACKET_GAP]
        for _ in range(PACKETS_PER_BURST):
            out += packet_timings(self.packet)
        return out

    def __repr__(self) -> str:
        """Return a concise representation for logging."""
        return f"El1039Command({self.packet.hex(' ')})"
