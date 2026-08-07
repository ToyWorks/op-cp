#!/bin/sh
# Print the serial port of the attached M5Stack board.
#
# mpremote's own device listing carries the USB manufacturer string, which is
# the only reliable discriminator here: a second /dev/cu.usbmodem* shows up for
# any USB monitor or dock, and picking the first one alphabetically gets it
# wrong about half the time.
set -e

MPREMOTE="${MPREMOTE:-mpremote}"

port=$("$MPREMOTE" devs 2>/dev/null | awk '$4 == "M5Stack" { print $1; exit }')

if [ -z "$port" ]; then
    echo "no M5Stack board found on USB." >&2
    echo "checked:" >&2
    "$MPREMOTE" devs 2>/dev/null | sed 's/^/  /' >&2
    exit 1
fi

echo "$port"
