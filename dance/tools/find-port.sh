#!/bin/sh
# Print the serial port of the board `make BOARD=...` asked for.
#
#   tools/find-port.sh cores3    # the CoreS3 on the StackChan base
#   tools/find-port.sh cube      # the xiaozhi-cube 1.54
#   tools/find-port.sh --list    # everything attached, with its BOARD= name
#
# Several M5-flavoured boards live on this desk — the Cardputer-ADV is the
# band — so matching on the manufacturer alone picks the wrong one. Match the
# product string that UIFlow2 puts in the USB descriptor instead.
#
# The cube answers to "StampS3" because that is the firmware it runs: M5 has
# no build for a board they never made, and the StampS3 image is the bare
# ESP32-S3 one (see boards/cube/scd_board.py). If a real StampS3 ever shares
# this hub, match on its serial number instead.
set -e

MPREMOTE="${MPREMOTE:-mpremote}"

case "${1:-cores3}" in
    cores3) want='[Cc]ore[Ss]3' ;;
    cube)   want='StampS3' ;;
    --list)
        "$MPREMOTE" devs 2>/dev/null | awk '
            $3 ~ /^303a:/ {
                name = "?"
                if ($0 ~ /[Cc]ore[Ss]3/)  name = "cores3"
                else if ($0 ~ /StampS3/)  name = "cube"
                printf "  BOARD=%-8s %s  %s\n", name, $1, substr($0, index($0, $4))
            }'
        exit 0 ;;
    *)
        echo "unknown board '$1' — expected cores3 or cube" >&2
        exit 1 ;;
esac

port=$("$MPREMOTE" devs 2>/dev/null | awk -v re="$want" '$0 ~ re { print $1; exit }')

if [ -z "$port" ]; then
    echo "no board matching /$want/ on USB." >&2
    echo "checked:" >&2
    "$MPREMOTE" devs 2>/dev/null | sed 's/^/  /' >&2
    exit 1
fi

echo "$port"
