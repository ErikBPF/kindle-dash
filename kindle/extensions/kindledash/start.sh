#!/bin/sh
# KUAL action: start the dashboard loop (idempotent — won't stack copies).
# Also runnable straight from kterm: sh /mnt/us/extensions/kindledash/start.sh
DASH=/mnt/us/documents/dashboard.sh

pkill -f "$DASH" 2>/dev/null
sleep 1

# Detach into a new session so KUAL exiting its menu (which tears down the
# action's process group) doesn't signal-kill the loop. setsid gives it a fresh
# session with no controlling terminal; nohup is the fallback.
if command -v setsid >/dev/null 2>&1; then
  setsid sh "$DASH" </dev/null >/dev/null 2>&1 &
else
  nohup sh "$DASH" </dev/null >/dev/null 2>&1 &
fi
