# EL1039 / RF290K radio protocol

This is how the Regency/Gazco **EL1039** handset (keypad PCB `RF290K`) talks to the fire, as measured with an RTL-SDR (R820T, 250 kS/s) against a Regency 223-088 electric fireplace. FCC ID `2AQ6Y-EL1039` (Gazco Ltd; made by Richen).

It is related to the older `RF290A` handset decoded by [esph-gazco-electric](https://github.com/richardctrimble/esph-gazco-electric) (same checksum, same S0 layout), but the timing, packet length and repeat count differ, so RF290A code won't drive these fires.

## Physical layer

The FCC test report says "FSK", but that's wrong. On air it's plain **OOK** at **433.92 MHz**: the carrier's frequency spread while keyed is 2–4 kHz.

Bits are coded by mark (carrier on) width; every space is the same length.

| Element | Mark | Space |
|---|---|---|
| Preamble, ×10 | 336 µs | 664 µs |
| Bit 0 | 140 µs | 564 µs |
| Bit 1 | 540 µs | 564 µs |
| Trailer | 20 ms carrier | ~10 ms |

- **One button press is one burst:** a 20 ms carrier and 10 ms gap, then **3 identical packets** (each preamble + 80 bits + trailer). That's about 300 ms in total.
- **The 10 ms gap between packets matters.** A Broadlink RM4 Pro using its own hardware repeat leaves ~17 ms gaps, and the fire ignores those bursts. This integration sends the whole burst as one timing list with `repeat_count = 0`.

## Packet

There are 80 bits, MSB first:

```
[ID_hi][ID_lo][S0][S1][S2][S3][S4][S5][CHK][~CHK]
```

| Field | Bits | Meaning |
|---|---|---|
| ID | 16 | Handset ID. The fire obeys exactly one ID (see Pairing). |
| S0 | bit 7 | **Flag.** Required on the pairing packet. Flagged packets never switch the fire on or off; the handset sets this bit on its periodic re-broadcasts. |
| S0 | bit 6 | Power: on / standby |
| S0 | bits 5–3 | Flame setting: `001` = flame on, `000` = flame off |
| S0 | bits 2–0 | Flame brightness, 1–5 |
| S1 | bits 7–5 | Fuel bed brightness, 1–5 |
| S1 | bits 4–0 | Fuel bed setting: `0` = off, `1`–`14` = colours (→ steps 0, 1 … 14, then wraps to 0) |
| S2 | bits 7–4 | Timer: `0` off, `1` = 0.5 h, `2`–`11` = 1–10 h; `F` in the handset's re-broadcasts while it runs. Not used by this integration. |
| S2 | bit 2 | Heating enabled |
| S3 | – | Always `00` |
| S4 | 8 | Heating setpoint, whole °C, 5–40 (the handset's limits) |
| S5 | 8 | Room temperature, whole °C, from the handset's own sensor |
| CHK | 8 | `(sum of the 8 bytes before it + 0x55) & 0xFF` |
| ~CHK | 8 | Bitwise complement of CHK |

Every packet carries the **whole state**. A transmitter that knows the ID can therefore set any combination directly, with no need to "press buttons" or learn codes.

Example: `ec 60 4d a3 00 00 14 18 bd 42` means ID `EC60`, on, flame 5, fuel bed setting 3 at brightness 5, heating off, setpoint 20 °C, room 24 °C.

## Thermostat

The fire runs the thermostat itself, from the room temperature in the last packet it received.

- The handset re-broadcasts its state (flagged) on a ~51.7 s tick, skipping some ticks.
- This integration does the same while heating, using the configured temperature source.
- It turns heating off if that source has had no reading for 10 minutes.

## Pairing

1. Hold the **pinhole reset button** on the fire's right-hand control panel (use a pen) until it beeps **3 times**. This opens a ~10 s learn window.
2. Within that window, send any packet with **S0 bit 7 set**. The fire learns its ID.
   - A packet with the flag clear is ignored during the learn window.
   - The learn packet does not itself turn the fire on; the next normal packet does.

Behaviour observed:

- **Any 16-bit ID can be paired.** Earlier guesses that the ID needs particular bits don't hold.
- **The fire stores one ID.** Pairing a new one locks out the previous one, including the original handset.
- **To share control with the original handset**, don't pair. Use the handset's own ID, which you can read with an SDR, for example `rtl_433 -f 433.92M -s 250k -A`.
- **The handset's own reset button** (under the back cover, hold 3 s) can make it choose a new ID.
- **Handset IDs survive battery changes.**

## °C / °F

Switching the handset's display to °F doesn't change any packet field. Temperatures are always sent in whole °C.

## Unverified

- **The names of the 14 fuel bed colours.** The integration calls them "Setting 1" to "Setting 14".
- **How the fire handles the timer,** for example whether re-sending a timer step restarts the countdown. That's why the integration leaves the timer to Home Assistant automations.
