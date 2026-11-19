"""Packets must match what the real handset and fire exchanged (captures/)."""

import pytest

from custom_components.regency_fireplace.protocol import (
    El1039Command,
    FireplaceState,
    build_packet,
)

# Packets decoded from SDR captures of a real EL1039 handset (ID EC60), each
# one either sent by the handset or accepted by the fire.
CAPTURED = [
    # handset defaults, on / off: flame 5, fuel bed 3 at brightness 5, set 20, room 24
    (0xEC60, FireplaceState(True, True, 5, 3, 5, False, 20, 24), False, "ec 60 4d a3 00 00 14 18 bd 42"),
    (0xEC60, FireplaceState(False, True, 5, 3, 5, False, 20, 24), False, "ec 60 0d a3 00 00 14 18 7d 82"),
    # handset after a battery change: flagged (S0 bit 7), off, room 23
    (0xEC60, FireplaceState(False, True, 5, 3, 5, False, 20, 23), True, "ec 60 8d a3 00 00 14 17 fc 03"),
    # sent through a Broadlink RM4 Pro; the fire turned on: flame 1, fuel 6/1, set 19, room 25
    (0xEC60, FireplaceState(True, True, 1, 6, 1, False, 19, 25), False, "ec 60 49 26 00 00 13 19 3c c3"),
]


@pytest.mark.parametrize(("fire_id", "state", "flag", "expected"), CAPTURED)
def test_packets_match_captures(fire_id, state, flag, expected) -> None:
    """Byte-exact against the captures."""
    assert build_packet(fire_id, state, flag).hex(" ") == expected


# S0..S5 captured from the handset while stepping through every setting
# (flame off, fuel bed 0-14, fuel brightness, setpoint 5-40, heating on/off).
CAPTURED_STATE = [
    (FireplaceState(True, True, 5, 0, 5, False, 20, 22), False, "4d a0 00 00 14 16"),
    (FireplaceState(True, False, 5, 0, 5, False, 20, 22), False, "45 a0 00 00 14 16"),  # flame off
    (FireplaceState(True, False, 5, 1, 5, False, 20, 22), False, "45 a1 00 00 14 16"),
    (FireplaceState(True, False, 5, 14, 5, False, 20, 22), False, "45 ae 00 00 14 16"),
    (FireplaceState(True, False, 5, 0, 3, False, 20, 23), False, "45 60 00 00 14 17"),
    (FireplaceState(True, False, 5, 0, 1, False, 20, 23), False, "45 20 00 00 14 17"),  # fuel bed off
    (FireplaceState(True, False, 5, 0, 1, True, 20, 23), False, "45 20 04 00 14 17"),  # heating on
    (FireplaceState(True, False, 5, 0, 1, True, 40, 23), False, "45 20 04 00 28 17"),  # max setpoint
    (FireplaceState(True, False, 5, 0, 1, True, 5, 23), False, "45 20 04 00 05 17"),  # min setpoint
    (FireplaceState(False, False, 5, 0, 1, False, 5, 23), True, "85 20 00 00 05 17"),
    (FireplaceState(True, True, 5, 0, 1, False, 5, 23), True, "cd 20 00 00 05 17"),
]


@pytest.mark.parametrize(("state", "flag", "expected"), CAPTURED_STATE)
def test_state_bytes_match_captures(state, flag, expected) -> None:
    """S0..S5 byte-exact against the handset."""
    assert state.state_bytes(flag).hex(" ") == expected


def _decode(timings: list[int]) -> list[bytes]:
    """Minimal receiver: split on long marks, skip preamble, threshold marks."""
    packets, bits = [], ""
    for t in timings:
        if t <= 0:
            continue
        if t > 5000:
            if bits:
                packets.append(int(bits, 2).to_bytes(10, "big"))
            bits = ""
        elif 240 <= t < 440 and not bits:
            continue
        else:
            bits += "1" if t >= 340 else "0"
    return packets


def test_burst_shape() -> None:
    """Wake-up carrier, then 3 packets each ending in a 20 ms carrier + 10 ms gap."""
    cmd = El1039Command(0xA1B2, FireplaceState(power=True), flag=False)
    t = cmd.get_raw_timings()
    assert cmd.repeat_count == 0 and cmd.frequency == 433_920_000
    assert t[:2] == [20_030, -10_080]
    assert t[-2:] == [20_030, -10_080]
    assert all((v > 0) == (i % 2 == 0) for i, v in enumerate(t))  # strictly alternating
    assert _decode(t) == [cmd.packet] * 3
    assert len(t) == 2 + 3 * (20 + 160 + 2)


@pytest.mark.parametrize(
    "bad",
    [
        {"flame_brightness": 0},
        {"fuel_brightness": 6},
        {"fuel_setting": 15},
        {"setpoint": 4},
        {"setpoint": 41},
    ],
)
def test_out_of_range_rejected(bad) -> None:
    """A bad value can never reach the fire."""
    with pytest.raises(ValueError):
        FireplaceState(**bad)
