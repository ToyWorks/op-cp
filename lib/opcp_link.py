# OP-CP — the ESP-NOW mouth: broadcast each step as it plays.
#
# The StackChan across the desk dances better from ground truth than from
# its microphone: 9 bytes per sixteenth tell it the step, which tracks
# fired, which drum, and the tempo. Broadcast, connectionless, no pairing;
# channel 1 on both ends. ctrl+N toggles it; the radio comes up lazily on
# first use so a link left off costs nothing.
#
# Wire format, shared with scd_link.py on the StackChan (keep in sync):
#   0:2  b'oc'    magic
#   2    ver      1
#   3    type     1 = step, 2 = transport
#   step:      4 step 0-15, 5 hits bitmask (bit t = track t fired),
#              6 drum index (255 = no PERC), 7:9 bpm u16le
#   transport: 4 playing 0/1, 5:7 bpm u16le

import opcp_conf as C
from opcp_state import S

_e = None
_bcast = b'\xff\xff\xff\xff\xff\xff'
ok = False


def begin():
    global _e, ok
    if _e is not None:
        return ok
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
            sta.config(channel=C.LINK_CHANNEL)
        except Exception:
            pass
        _e = espnow.ESPNow()
        _e.active(True)
        _e.add_peer(_bcast)
        ok = True
    except Exception:
        ok = False
    return ok


def send_step(step, hits, drum):
    if not ok:
        return
    try:
        _e.send(_bcast, bytes((0x6F, 0x63, 1, 1, step, hits, drum,
                               S.bpm & 0xFF, S.bpm >> 8)), False)
    except Exception:
        pass


def send_transport(playing):
    if not ok:
        return
    try:
        _e.send(_bcast, bytes((0x6F, 0x63, 1, 2, 1 if playing else 0,
                               S.bpm & 0xFF, S.bpm >> 8)), False)
    except Exception:
        pass
