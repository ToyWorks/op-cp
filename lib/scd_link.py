# SCD — the ESP-NOW ear: when OP-CP is broadcasting, dance to ground truth.
#
# The Cardputer knows exactly which step fired and what played on it; a
# 9-byte broadcast beats any amount of onset detection. The microphone
# stays as the fallback — no packets for LINK_FRESH_MS and the mic path
# takes over again, automatically.
#
# Wire format, shared with opcp_link.py on the Cardputer (keep in sync):
#   0:2  b'oc'    magic
#   2    ver      1
#   3    type     1 = step, 2 = transport
#   step:      4 step 0-15, 5 hits bitmask (bit t = track t fired,
#              LEAD/BASS/KEYS/PERC), 6 drum index (255 = no PERC), 7:9 bpm u16le
#   transport: 4 playing 0/1, 5:7 bpm u16le

import scd_conf as C
from scd_state import S

_e = None
ok = False


def begin():
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
            sta.config(channel=C.LINK_CHANNEL)
        except Exception:
            pass
        _e = espnow.ESPNow()
        _e.active(True)
        ok = True
    except Exception:
        _e = None
        ok = False


def parse(msg, now):
    """One packet in; beat intensity out (0 = none). Pure, selftest-fed.

    BD hits hard, SD/CP mark the backbeat, hats and melody only breathe
    the level — a hand that tapped every 16th would be a blur, not a beat.
    """
    if msg is None or len(msg) < 4 or msg[0] != 0x6F or msg[1] != 0x63 \
            or msg[2] != 1:
        return 0
    t = msg[3]
    if t == 2 and len(msg) >= 7:
        S.link_last = now
        bpm = msg[5] | (msg[6] << 8)
        if 40 <= bpm <= 240:
            S.bpm = bpm
            S.ibi = 60000 // bpm
        if not msg[4]:
            S.link_stop = True
        return 0
    if t != 1 or len(msg) < 9:
        return 0
    S.link_last = now
    step, hits, drum = msg[4], msg[5], msg[6]
    bpm = msg[7] | (msg[8] << 8)
    if 40 <= bpm <= 240:
        S.bpm = bpm
        S.ibi = 60000 // bpm

    bump = 0
    inten = 0
    if hits & 0x08:                       # PERC fired
        if drum == 0:                     # BD
            inten, bump = 3, 110
        elif drum in (1, 7):              # SD / CP
            inten, bump = 2, 90
        else:                             # hats, rim, toms, cowbell
            inten, bump = 0, 45
    if hits & 0x07:                       # melody breathes the level
        bump += 25
        if not inten and step % 4 == 0:   # drumless music still has bars
            inten = 2
    if bump:
        lv = S.level + bump
        S.level = C.LEVEL_MAX if lv > C.LEVEL_MAX else lv
    return inten


def poll(now):
    """Drain everything pending; the strongest packet wins this pass."""
    if _e is None or not S.link_enabled:
        return 0
    best = 0
    try:
        while _e.any():
            _mac, msg = _e.irecv(0)
            i = parse(msg, now)
            if i > best:
                best = i
    except Exception:
        return 0
    return best


def fresh(now):
    return ok and S.link_enabled and (now - S.link_last) < C.LINK_FRESH_MS
