# The stage node's ear: OP-CP's step broadcast, received.
#
# Adapted from vendor/op-cp/dance/lib/scd_link.py, which solved this already.
# What changed: the dancer turned packets into an animation intensity, and a
# stage node turns them into liveness and tempo — so parse() returns facts, not
# a beat strength, and nothing here draws.
#
# Wire format, shared with opcp_link.py on the Cardputer (change one, change
# both):
#   0:2  b'oc'    magic
#   2    ver      1
#   3    type     1 = step, 2 = transport
#   step:      4 step 0-15, 5 hits bitmask (bit t = track t fired),
#              6 drum index (255 = no PERC), 7:9 bpm u16le
#   transport: 4 playing 0/1, 5:7 bpm u16le
#
# This is a listener and only a listener. It never transmits, so no failure in
# here can reach the sequencer.

# The wire facts live HERE, with the code that speaks them. Shared with
# ../lib/opcp_link.py and ../dance/lib/scd_link.py — change one, change all.
LINK_CHANNEL = 1
LINK_FRESH_MS = 1500     # packets younger than this mean the show is live

_e = None
ok = False


def begin():
    """Bring up the radio. Failure is not fatal — a node with no ear still
    shows status and still stops the show."""
    global _e, ok
    try:
        import espnow
        import network
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        try:
            sta.disconnect()
        except Exception:
            pass
        try:
            sta.config(channel=LINK_CHANNEL)
        except Exception:
            pass
        _e = espnow.ESPNow()
        _e.active(True)
        ok = True
    except Exception:
        _e = None
        ok = False
    return ok


def parse(msg):
    """One packet in, facts out, or None if it is not ours.

    Pure: no hardware, no globals mutated. The conformance suite feeds it
    bytes directly, which is the only way to test a radio without one.
    """
    if msg is None or len(msg) < 4 or msg[0] != 0x6F or msg[1] != 0x63 \
            or msg[2] != 1:
        return None
    kind = msg[3]
    if kind == 2 and len(msg) >= 7:
        bpm = msg[5] | (msg[6] << 8)
        return {"kind": "transport", "playing": bool(msg[4]),
                "bpm": bpm if 40 <= bpm <= 240 else None}
    if kind == 1 and len(msg) >= 9:
        bpm = msg[7] | (msg[8] << 8)
        return {"kind": "step", "step": msg[4], "hits": msg[5],
                "drum": msg[6], "bpm": bpm if 40 <= bpm <= 240 else None}
    return None


def poll():
    """Drain what is pending and return the parsed packets. Never blocks."""
    if _e is None:
        return []
    out = []
    try:
        while _e.any():
            _mac, msg = _e.irecv(0)
            fact = parse(msg)
            if fact is not None:
                out.append(fact)
    except Exception:
        return out
    return out
