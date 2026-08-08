#!/bin/sh
# Print the serial port of the attached CoreS3 (the StackChan's head).
#
# Two M5Stack boards live on this desk — the Cardputer-ADV is the band, the
# CoreS3 is the dancer — so matching on the manufacturer string alone picks
# the wrong one half the time. Match the product string instead.
set -e

MPREMOTE="${MPREMOTE:-mpremote}"

port=$("$MPREMOTE" devs 2>/dev/null | awk '$4 == "M5Stack" && $5 ~ /[Cc]ore[Ss]3/ { print $1; exit }')

if [ -z "$port" ]; then
    echo "no CoreS3 found on USB." >&2
    echo "checked:" >&2
    "$MPREMOTE" devs 2>/dev/null | sed 's/^/  /' >&2
    exit 1
fi

echo "$port"
