# Widgets

The renderer is **slot-based**. `render()` defines a grid of boxes and hands each to a widget. A widget is just two things:

1. a **fetch** function that returns data (or `None` — fail soft, always), and
2. a **draw** function `w_<name>(d, box, …)` that paints inside `box = (x, y, w, h)`.

Everything scales off the box height, so a widget works at any resolution and in any slot.

## Add a widget in ~20 lines

```python
def fetch_aqi():
    data = _ha_get("/api/states/sensor.air_quality")  # or any source; return None on failure
    return data and data.get("state")

def w_aqi(d, box):
    x, y, w, h = box
    aqi = fetch_aqi()
    d.text((x, y), "AIR", font=_font(True, h * 0.2), fill=0)
    d.text((x, y + h * 0.3), aqi or "—", font=_font(False, h * 0.5), fill=0)
```

Then give it a box in `render()`:

```python
w_aqi(d, (mid, mid_y, rcol, (mid_b - mid_y) * 0.5))
```

Conventions: pure black on white (e-ink is sharpest at 1-bit); size fonts as a fraction of `h`; truncate text with `_trunc()`; never raise out of a widget (a thrown widget shouldn't break the whole frame — wrap risky fetches).

## Shipped in v1

Clock · Weather (now) · Forecast (N-day) · Agenda (HA calendar) · Sun & Moon (HA sun + local moon phase) · Claude usage (Session/Week/Sonnet).

## Roadmap — proposed widgets

| Widget | Source | Effort | Notes |
|---|---|---|---|
| **Now playing** | HA `media_player` / Plex / Jellyfin | low | track/show + artist; hide when idle |
| **Service health** | HTTP/ping checks, or Uptime-Kuma | med | up/down dots for key services |
| **To-do / tasks** | HA `todo.*` / Todoist / a markdown file | low | top N open items |
| **Transit / commute** | GTFS or a transit API | med | next departures for a stop |
| **Markets** | a stocks/crypto API | low | small watchlist, % change |
| **Daily flavor** | bundled list / API | low | quote / word / on-this-day — zero-data charm |
| **Photo / art frame** | a folder of images | med | rotate dithered grayscale art; e-ink loves this |
| **Habit / streak** | a counter file / HA | low | "N days since X" |
| **Air quality / pollen** | HA / AQI API | low | number + trend |
| **Countdown** | a configured date | low | "12 days until …" |
| **Kindle battery** | device-side (`gasgauge`/`lipc`) | low | drawn on-device or POSTed back |

PRs that add a widget should keep it **optional** (no config → hidden) and **fail soft**. If it needs a new dependency, say why in the PR.

## Layout

`render()` is the single place layout lives — a handful of box tuples. Rearrange, resize, or swap widgets there. If you want a fundamentally different grid (e.g. a portrait-native layout, or a rotating multi-screen), that's a `render()` change, not a widget change.
