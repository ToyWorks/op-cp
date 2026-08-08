# Runs ON THE DEVICE. Dumps real font metrics so the host simulator lays out
# text exactly as the panel does. Without this the sim is a guess.
import M5
M5.begin()

FONTS = ("DejaVu9", "DejaVu12", "DejaVu18", "DejaVu24", "DejaVu40",
         "DejaVu56", "DejaVu72", "Montserrat12", "Montserrat14",
         "Montserrat16", "Montserrat18", "Montserrat24", "Montserrat40",
         "Montserrat44", "Montserrat48", "ASCII7")

print("{")
print('"screen": [%d, %d],' % (M5.Lcd.width(), M5.Lcd.height()))
print('"fonts": {')
first = True
for name in FONTS:
    f = getattr(M5.Lcd.FONTS, name, None)
    if f is None:
        continue
    M5.Lcd.setFont(f)
    widths = [M5.Lcd.textWidth(chr(c)) for c in range(32, 127)]
    # additivity probe: if textWidth(s) == sum(widths of chars) there is no
    # kerning and the host can compose widths per character.
    probe = "Wave 108"
    add = sum(widths[ord(c) - 32] for c in probe)
    if not first:
        print(",")
    first = False
    print('"%s": {"h": %d, "w": %s, "probe": [%d, %d]}'
          % (name, M5.Lcd.fontHeight(), widths, M5.Lcd.textWidth(probe), add), end="")
print("\n}}")
