#!/bin/sh
# KUAL action: stop the dashboard loop cleanly, no reboot needed.
# The TERM trap in dashboard.sh restores the screensaver + clears the screen;
# the lines below are a backstop in case it was killed hard.
DASH=/mnt/us/documents/dashboard.sh

pkill -TERM -f "$DASH" 2>/dev/null
sleep 1
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
command -v eips >/dev/null 2>&1 && eips -c 2>/dev/null
