# OP-CP — an OP-1 flavoured keyboard sequencer for the M5Stack Cardputer-ADV.
#
# Keybed: the middle two keyboard rows are a piano — white keys on the home row,
# black keys in the physical gaps above them.
#
#        w e   t y u   o p          black keys
#       a s d f g h j k l ;         white keys  C D E F G A B C D E
#
#   1 2 3 4 5 6 7 8                 steps 1-8
#   z x c v b n m ,                 steps 9-16
#
#   SPACE play/stop     ENTER record arm (live, quantized to 16ths)
#   ctrl+G generate   ctrl+C clear   ctrl+M mute   ctrl+P pattern
#   ctrl+[ ] tempo    ctrl+F files   - = octave   ` scale   9 swing   0 volume
#   . / previous / next track        \ next view (help is the last one)
#   FILES view: 1-8 load a slot, s then 1-8 save, w e t y drop in a preset
#
# This file is only the lifecycle. Everything else lives in lib/, which the
# Makefile installs next to main.py on the device:
#
#   opcp_conf     constants: palette, musical tables, key maps        (no state)
#   opcp_state    S — every mutable field, in one object
#   opcp_audio    the mixer and the voices
#   opcp_ui       fonts, layout, the roll, the header, the footer, help
#   opcp_screen   the three alternate views + the full-screen compositor
#   opcp_seq      pattern generation, the transport clock, persistence
#   opcp_keys     the keyboard bindings
#
# Import direction is strictly one way — conf <- state <- audio/ui <- screen <-
# seq <- keys <- here — so nothing imports in a cycle.

import time

import M5

import opcp_audio as A
import opcp_conf as C
import opcp_keys as K
import opcp_screen as SC
import opcp_seq as Q
import opcp_ui as U
from opcp_state import S


def setup():
    M5.begin()
    U.layout()                       # reads width/height; never hardcode them
    M5.Lcd.fillScreen(C.BG)
    try:
        M5.Lcd.setBrightness(150)
    except Exception:
        pass

    A.begin()
    Q.storage_init()                 # SD if a card is in, /flash otherwise
    if S.link_on:
        import opcp_link
        opcp_link.begin()            # broadcast steps for the StackChan

    # Optional hardware: a plain Cardputer has no matrix keyboard, and the
    # program should still run and show its screen if this fails.
    try:
        from hardware import MatrixKeyboard
        S.kb = MatrixKeyboard()
        S.kb.set_callback(K.on_key)
        S.kb_tick = getattr(S.kb, "tick", None)
    except Exception:
        S.kb = None
        S.kb_tick = None

    Q.generate()
    SC.redraw_all()


def loop():
    M5.update()
    if S.kb_tick:
        try:
            S.kb_tick()
        except Exception:
            pass

    if S.dirty_all:
        S.dirty_all = False
        S.dirty_body = False
        SC.redraw_all()
    elif S.dirty_body:
        S.dirty_body = False
        SC.redraw_body()

    A.flush_pending()

    if S.playing and time.ticks_diff(time.ticks_ms(), S.next_tick) >= 0:
        Q.advance()

    Q.decay_flashes()
    if S.view in (C.V_FACE, C.V_RING, C.V_BARS):
        SC.animate()

    # The hero value falls back to the tempo on its own and a status word
    # expires out of the header; both need a repaint nobody asked for.
    if S.view != C.V_HELP:
        if U.footer_changed():
            U.draw_footer()
        if U.head_changed():
            U.draw_head()

    time.sleep_ms(2)


if __name__ == '__main__':
    try:
        setup()
        while True:
            loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
