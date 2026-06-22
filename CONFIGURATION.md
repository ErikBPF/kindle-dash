# Configuration

All renderer config is environment variables (in `renderer/.env`; see `.env.example`). Everything except resolution is optional — an unconfigured panel renders a quiet placeholder.

## Display

| Var | Default | Notes |
|---|---|---|
| `KINDLE_W` / `KINDLE_H` | `1024` / `758` | **Landscape** (width ≥ height). Must match your panel — check `cat /sys/class/graphics/fb0/virtual_size` on the device. PW2 = `1024×758`, PW3+/Oasis = `1448×1072`. |
| `TZ` | `UTC` | IANA tz, e.g. `America/Sao_Paulo`. Drives the clock + all formatted times. |
| `DASH_ROTATE` | `0` | `0/90/180/270`. Rotates the frame **server-side** — `90` fills a portrait panel mounted sideways (`270` if upside down). |
| `DASH_DARK` | `0` | `1` = light-on-black (e-ink dark mode; the whole frame is inverted). |
| `DASH_WIDGETS` | all | Comma list of panels to draw, in order: `clock,weather,forecast,agenda,sunmoon,usage`. Drop any to hide it. |
| `PORT` | `8810` | Host port the container publishes (compose). |
| `DASH_FONT_DIR` | `/usr/share/fonts/truetype/dejavu` | Where the DejaVu TTFs live (the image ships them). |

> **All visual options live here, not on the device.** Rotation, dark mode, and the widget set are container env — the Kindle only ever opens the bare `GET /dash.png`. Change a knob, recreate the container, done; nothing to touch on the Kindle.

## Home Assistant (weather · forecast · sun · agenda)

Optional. Create a long-lived token: HA → Profile → Security → Long-lived access tokens.

| Var | Example | Powers |
|---|---|---|
| `HA_BASE_URL` | `http://192.168.1.5:8123` | all HA panels (blank = all off) |
| `HA_TOKEN` | `eyJ…` | auth |
| `HA_WEATHER_ENTITY` | `weather.home` | weather **and** the forecast strip |
| `HA_CALENDAR_ENTITY` | `calendar.personal` | agenda (blank = hidden) |
| `HA_SUN_ENTITY` | `sun.sun` | sunrise/sunset (moon phase is computed locally, no entity needed) |
| `FORECAST_DAYS` | `3` | days in the forecast strip |
| `DASH_MAX_EVENTS` | `4` | agenda rows |

Forecast uses HA's `weather.get_forecasts` service; if your weather integration doesn't support daily forecasts, the strip just hides.

## Claude usage (Session / Week / Sonnet)

Optional. **Read [SECURITY.md](SECURITY.md) first** — it's an undocumented API and you should give the dashboard its own login.

| Var | Default | Notes |
|---|---|---|
| `CLAUDE_REFRESH_TOKEN` | — | seed from a dedicated login (see SECURITY.md). Blank = panel off. |
| `CLAUDE_POLL_MIN` | `15` | minutes between usage refreshes |
| `CLAUDE_CLIENT_ID` | Claude Code's public id | rarely changes |
| `CLAUDE_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | token refresh endpoint |
| `CLAUDE_USAGE_URL` | `https://api.anthropic.com/api/oauth/usage` | usage endpoint |
| `CLAUDE_STALE_AFTER_MIN` | `45` | after this with no successful fetch, the panel shows `(stale)` |

The renderer persists rotated tokens to `/data/claude_tokens.json` (mount the volume so they survive restarts). The `CLAUDE_REFRESH_TOKEN` env is only a **seed** used on first run.

## Device (`dashboard.sh`)

| Var | Default | Notes |
|---|---|---|
| `DASH_URL` | `http://CHANGE-ME.lan/dash.png?rotate=90` | where the device fetches; set to your renderer |
| `FULL_EVERY` | `30` | full (flashing) de-ghost refresh every N minute-cycles |
| `LOG` | `/tmp/kindle-dash.log` | script log (kept off-screen) |
