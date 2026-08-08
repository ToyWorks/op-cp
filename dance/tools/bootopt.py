# Make the board run main.py on power-up. `make deploy` runs this first.
#
# UIFlow2's boot.py (m5stack/fs/user/boot.py) reads NVS uiflow/boot_option:
#   0 -> run main.py directly      1 -> startup menu + network (factory)
#   2 -> network only
#
# The trap: it reads with **get_u8**, and esp32.NVS types its keys. Write the
# key with set_i32 and get_i32 will happily read 0 back — while boot.py's
# get_u8 raises NOT_FOUND, falls back to 1, and spends 60 s trying to join a
# network instead of starting the app. Nothing anywhere reports an error, and
# an ST7789 holds its last image without refreshing, so the symptom is a
# screen that looks like a frozen app rather than one that never started.
# Hence: erase the key first (a wrongly-typed one of the same name is exactly
# what makes set_u8 alone insufficient), then write it as u8.

import esp32

nvs = esp32.NVS("uiflow")

try:
    nvs.erase_key("boot_option")
except Exception:
    pass

nvs.set_u8("boot_option", 0)
nvs.commit()
print("==> boot_option = %d (0 = run main.py directly)" % nvs.get_u8("boot_option"))
