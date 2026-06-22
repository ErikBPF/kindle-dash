#!/bin/sh
# dashboard.sh — run ON a jailbroken Kindle (tested on Paperwhite 2; works on
# most). Fetches the rendered PNG from the renderer and paints it on the e-ink
# screen, refreshing on a timer. A periodic full (flashing) refresh de-ghosts.
#
# Painter: prefers fbink (nicer partial refresh) but falls back to the stock
# `eips` that ships on every jailbroken Kindle — so no install is required.
# Requires curl (present on most jailbroken Kindles).
#
# SET THIS URL to wherever the renderer is reachable from the Kindle. The
# Kindle's ancient TLS can't do modern HTTPS, so serve plain HTTP (see
# docs/INSTALLATION.md for a reverse-proxy example). rotate=90 pre-rotates the
# landscape frame to fill a portrait framebuffer — mount the device sideways
# (use rotate=270 if it lands upside down; drop ?rotate= for a desktop browser).
URL="${DASH_URL:-http://CHANGE-ME.lan/dash.png?rotate=90}"
IMG="/tmp/dash.png"
LOG="${LOG:-/tmp/kindle-dash.log}"
FULL_EVERY=30      # full flashing refresh every N cycles (here: 30 min) to de-ghost
# Refresh once per minute, aligned to the top of the minute (see loop below) so
# the clock flips with the wall clock instead of drifting up to ~2 min behind.

# Send all our stdout/stderr to a logfile so curl/shell chatter never paints
# onto the e-ink console (eips draws the image straight to the panel, so the
# dashboard itself is unaffected). Tail it with: cat $LOG
exec >>"$LOG" 2>&1

# --- pick a painter -------------------------------------------------------
# fbink if available (override with FBINK=/path), else the built-in eips.
FBINK="${FBINK:-fbink}"
if ! command -v "$FBINK" >/dev/null 2>&1 && [ ! -x "$FBINK" ]; then
  for c in /mnt/us/fbink /mnt/us/bin/fbink /mnt/us/koreader/fbink \
           /mnt/us/extensions/fbink/bin/fbink /usr/local/bin/fbink; do
    [ -x "$c" ] && FBINK="$c" && break
  done
fi
if command -v "$FBINK" >/dev/null 2>&1 || [ -x "$FBINK" ]; then
  PAINT=fbink
elif command -v eips >/dev/null 2>&1; then
  PAINT=eips
else
  echo "no painter found (need fbink or the stock eips)" >&2
  exit 1
fi

paint() {  # $1 = 1 for a full flashing refresh, 0 for a fast partial one
  if [ "$PAINT" = fbink ]; then
    if [ "$1" = 1 ]; then "$FBINK" -c -f -g file="$IMG"
    else "$FBINK" -g file="$IMG"; fi
  else
    [ "$1" = 1 ] && eips -c          # clear (de-ghost) on the full cycle
    eips -g "$IMG"
  fi
}

# Clean shutdown: on stop (KUAL Stop / pkill -TERM), restore the screensaver and
# clear the screen so the Kindle returns to normal without a reboot.
cleanup() {
  lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
  command -v eips >/dev/null 2>&1 && eips -c 2>/dev/null
  exit 0
}
trap cleanup TERM INT

# Keep the screen from blanking while the dashboard is up.
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

i=0
while true; do
  if curl -s -m 30 -o "$IMG" "$URL"; then
    if [ $((i % FULL_EVERY)) -eq 0 ]; then paint 1; else paint 0; fi
  fi
  # else: keep the last frame up; retry next cycle (Wi-Fi blip, renderer reboot)
  i=$((i + 1))
  # Sleep until the top of the next minute so the clock stays in sync. Strip a
  # leading zero first — busybox ash reads $((08)) as bad octal and aborts, and
  # the bash-only 10# base prefix isn't available here.
  secs=$(date +%S)
  secs=${secs#0}
  sleep $((60 - secs))
done
