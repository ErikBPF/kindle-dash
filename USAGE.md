# Usage

## Start / Stop (KUAL)

Open KUAL → **Kindle Dashboard** → **Start** / **Stop**. Start launches the loop detached (it survives KUAL closing); Stop signals it to exit cleanly, restoring the screensaver and clearing the screen — no reboot.

> If the entry doesn't appear, exit KUAL fully and reopen it — it only scans `/mnt/us/extensions/` on launch.

From kterm, the same scripts work:

```sh
sh /mnt/us/extensions/kindledash/start.sh
sh /mnt/us/extensions/kindledash/stop.sh
```

## How it refreshes

`dashboard.sh` fetches `/dash.png` once per minute, **aligned to the top of the minute** so the clock flips with the wall clock instead of drifting. Every `FULL_EVERY` cycles (default 30 min) it does a full flashing refresh to clear e-ink ghosting; in between it uses fast partial refreshes.

Don't go sub-minute: the clock is minute-resolution, so faster only adds ghosting, flicker, and battery drain for no visible change.

If a fetch fails (Wi-Fi blip, renderer restart) the **last good frame stays up** and it retries next cycle.

## Power

Preventing the screensaver + keeping Wi-Fi on drains faster than reading. For a wall dashboard, leave it on a USB charger — then it runs indefinitely.

## Survive reboots

Have your jailbreak's boot hook run `sh /mnt/us/extensions/kindledash/start.sh` (varies by model/firmware — don't edit stock init blindly).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Dashboard appears then **quits instantly** | start it detached (`setsid`, which `start.sh` does) — KUAL signal-kills non-detached children when its menu exits. |
| **Aborts after the first paint** in kterm | a non-POSIX shell-ism. The device runs busybox `ash`; test scripts with `sh -n`. |
| `eips: not found` | rare; confirm you're on a jailbroken Kindle, or drop `fbink` at `/mnt/us/fbink`. |
| Image **clipped / sideways** | resolution mismatch (`KINDLE_W/H`) or wrong `?rotate=` (try 90 vs 270). |
| Browser **redirects to https** | your browser auto-upgrades http→https; the device (curl) is unaffected. Add a `:443` vhost if you want browser access. |
| `(stale)` on the usage panel | renderer hasn't fetched usage recently — check its logs (`docker logs kindle-dash`); often a token issue (see [SECURITY.md](SECURITY.md)). |
| A panel shows a placeholder | its source isn't configured (or that fetch failed) — see [CONFIGURATION.md](CONFIGURATION.md). |

Device logs go to `/tmp/kindle-dash.log` (kept off-screen). Renderer logs: `docker logs kindle-dash`.
