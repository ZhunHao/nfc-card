#!/usr/bin/env bash
# Program one card end to end: signature, fuses, flash, verify.
#
#   firmware/tools/program-card.sh <label> [--diagnostic]
#
# <label> names the log folder (firmware/build/readback/<label>/), e.g. orbit-03.
# --diagnostic flashes diagnostic.hex instead of card.hex (walks D1-D20).
#
# Every step retries until it succeeds, so R6 can be bridged with tweezers:
# hold the bridge and the script moves on by itself. Fuses already at the target
# values are left alone. Env overrides: AVRDUDE, BOARD, PROGRAMMER, PORT, TRIES.
set -euo pipefail

AVRDUDE=${AVRDUDE:-/opt/homebrew/bin/avrdude}
BOARD=${BOARD:-orbit}
PROGRAMMER=${PROGRAMMER:-serialupdi}
PORT=${PORT:-/dev/cu.usbserial-110}
TRIES=${TRIES:-60}

label=${1:?usage: program-card.sh <label> [--diagnostic]}
image=card
[[ ${2:-} == --diagnostic ]] && image=diagnostic

root=$(cd "$(dirname "$0")/../.." && pwd)
hex="$root/firmware/build/$BOARD/release/$image.hex"
logs="$root/firmware/build/readback/$label"
[[ -f $hex ]] || { echo "missing $hex: run make -C firmware release BOARD=$BOARD" >&2; exit 1; }
mkdir -p "$logs"

# The fields the firmware needs (firmware/README.md, "Set the four required fields").
want=(freqsel=fcpu_16mhz bodactive=bod_enabled bodlevel=bod_1v8 sut=sut_0ms)

dude() { "$AVRDUDE" -p t1616 -c "$PROGRAMMER" -P "$PORT" "$@"; }

# retry <name> <check> -- avrdude args: rerun until avrdude exits 0 and <check> accepts the log.
retry() {
    local name=$1 check=$2; shift 3
    local log="$logs/$name.txt" i
    for ((i = 1; i <= TRIES; i++)); do
        if dude "$@" >"$log" 2>&1 && $check "$log"; then
            echo "  ok   $name (attempt $i)"; return 0
        fi
        printf '  ...  %s, attempt %d failed: %s\n' "$name" "$i" \
            "$(grep -m1 -i 'error' "$log" || echo 'check failed')"
        sleep 1
    done
    echo "FAIL $name after $TRIES attempts, see $log" >&2; exit 1
}

ok() { :; }
sig_ok() { grep -qx '0x1e,0x94,0x21' "$1"; }
updi_ok() { grep -q '^config rstpincfg=updi' "$1"; }
fuses_ok() {
    updi_ok "$1" || return 1
    local f; for f in "${want[@]}"; do grep -q "^config $f " "$1" || return 1; done
}
flash_ok() { grep -q 'bytes of flash verified' "$1"; }

echo "== $label: $BOARD $image.hex via $PROGRAMMER on $PORT"
echo "   bridge R6 and keep it bridged; each step retries until it succeeds"

retry signature sig_ok -- -U signature:r:-:h
retry fuses-before updi_ok -- -T 'config -f'

if fuses_ok "$logs/fuses-before.txt"; then
    echo "  ok   fuses already set"
    cp "$logs/fuses-before.txt" "$logs/fuses-after.txt"
else
    retry fuses-write ok -- -T "config ${want[0]}" -T "config ${want[1]}" \
        -T "config ${want[2]}" -T "config ${want[3]}"
    retry fuses-after fuses_ok -- -T 'config -f'
fi

retry flash flash_ok -- -U "flash:w:$hex:i" -U "flash:v:$hex:i"

echo "== $label done: $image.hex verified, fuses ${want[*]} rstpincfg=updi"
echo "   logs: $logs"
