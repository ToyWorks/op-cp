# Dump the API surface this board actually has. Run with `make probe`.
#
# The single most common way a UIFlow2 program fails is calling a method that
# does not exist on this firmware build. The fix is not to reason about it --
# it is to ask the board. Run this, read the lists, then write the call.
#
# One trap worth knowing: do NOT call dir() on the `hardware` package. Importing
# it is fast, but enumerating it makes MicroPython import every submodule, which
# initialises peripherals and wedges the REPL until the board is power-cycled.
# Import the class you want and dir() that instead, as done below.

import gc
import os
import sys

import M5

M5.begin()


def show(title, obj):
    try:
        names = sorted(n for n in dir(obj) if not n.startswith("_"))
    except Exception as e:
        print("%s: ERROR %r" % (title, e))
        return
    print("\n%s (%d)" % (title, len(names)))
    line = "  "
    for n in names:
        if len(line) + len(n) > 76:
            print(line)
            line = "  "
        line += n + " "
    if line.strip():
        print(line)


print("=" * 78)
print("firmware   %s" % (os.uname().version,))
print("machine    %s" % (os.uname().machine,))
print("mpy        %s" % (sys.implementation,))
print("board id   %s" % (getattr(M5, "getBoard", lambda: "?")(),))
print("screen     %dx%d" % (M5.Lcd.width(), M5.Lcd.height()))
print("=" * 78)

show("M5", M5)
show("M5.Lcd", M5.Lcd)
show("M5.Lcd.FONTS", M5.Lcd.FONTS)
show("M5.Speaker", M5.Speaker)
show("M5.Power", getattr(M5, "Power", None))

for mod, cls in (("hardware", "MatrixKeyboard"),
                 ("hardware", "Rtc"),
                 ("hardware", "I2C"),
                 ("hardware", "Pin")):
    try:
        m = __import__(mod)
        show("%s.%s" % (mod, cls), getattr(m, cls))
    except Exception as e:
        print("\n%s.%s: unavailable (%r)" % (mod, cls, e))

gc.collect()
print("\nfree heap  %d bytes" % gc.mem_free())
