#!/usr/bin/env python3
"""kindle-dash — render a grayscale dashboard PNG for a jailbroken Kindle.

A small HTTP server that renders a dashboard image sized to a Kindle's e-ink
screen. The Kindle fetches GET /dash.png on a timer and paints it with eips.

Endpoints:
  GET /dash.png[?rotate=90]   Rendered dashboard (grayscale PNG). rotate spins
                              the image so a landscape design fills a portrait
                              framebuffer when the device is mounted sideways.
  GET /healthz                Liveness probe.

Layout is slot-based: render() lays out a grid of boxes and hands each to a
widget — a function `w_<name>(draw, box, ...)` that draws inside its box. Add a
widget by writing a fetch + a w_ function and giving it a box (see WIDGETS.md).

Everything is config via env (see CONFIGURATION.md / .env.example). All external
fetches fail soft: a missing source renders a placeholder, never a broken image.
"""
import functools
import json
import math
import os
import threading
import time
import zoneinfo
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont

# --- config ----------------------------------------------------------------
KINDLE_W = int(os.environ.get("KINDLE_W", "1024"))
KINDLE_H = int(os.environ.get("KINDLE_H", "758"))
TZ = os.environ.get("TZ", "UTC")
TZINFO = zoneinfo.ZoneInfo(TZ)

# Home Assistant (optional) — powers weather, forecast, sun, and agenda widgets.
HA_BASE_URL = os.environ.get("HA_BASE_URL", "").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
HA_WEATHER_ENTITY = os.environ.get("HA_WEATHER_ENTITY", "")
HA_CALENDAR_ENTITY = os.environ.get("HA_CALENDAR_ENTITY", "")
HA_SUN_ENTITY = os.environ.get("HA_SUN_ENTITY", "sun.sun")
FORECAST_DAYS = int(os.environ.get("FORECAST_DAYS", "3"))
MAX_EVENTS = int(os.environ.get("DASH_MAX_EVENTS", "4"))
DASH_POLL_MIN = int(os.environ.get("DASH_POLL_MIN", "5"))  # HA refresh cadence

# Claude usage (optional) — fetched from the OAuth usage API; the short-lived
# access token is refreshed from a seeded refresh token (its OWN login — see
# SECURITY.md). Tokens persist to TOKEN_FILE so rotations survive restarts.
CLAUDE_REFRESH_TOKEN = os.environ.get("CLAUDE_REFRESH_TOKEN", "")
CLAUDE_CLIENT_ID = os.environ.get("CLAUDE_CLIENT_ID", "9d1c250a-e61b-44d9-88ed-5944d1962f5e")
CLAUDE_TOKEN_URL = os.environ.get("CLAUDE_TOKEN_URL", "https://api.anthropic.com/v1/oauth/token")
CLAUDE_USAGE_URL = os.environ.get("CLAUDE_USAGE_URL", "https://api.anthropic.com/api/oauth/usage")
# The usage endpoint puts requests with no claude-code-style User-Agent into an
# aggressively rate-limited bucket (persistent 429s). Send one.
CLAUDE_USER_AGENT = os.environ.get("CLAUDE_USER_AGENT", "claude-cli/2.1.179 (external, cli)")
CLAUDE_POLL_MIN = int(os.environ.get("CLAUDE_POLL_MIN", "15"))

STATE_DIR = os.environ.get("DASH_STATE_DIR", "/data")
STALE_AFTER_MIN = int(os.environ.get("CLAUDE_STALE_AFTER_MIN", "45"))
USAGE_FILE = os.path.join(STATE_DIR, "claude_usage.json")
TOKEN_FILE = os.path.join(STATE_DIR, "claude_tokens.json")
FONT_DIR = os.environ.get("DASH_FONT_DIR", "/usr/share/fonts/truetype/dejavu")


@functools.lru_cache(maxsize=None)
def _font(bold, size):
    # Fonts are immutable for the process; cache so we don't re-read+parse the
    # TTF on every text call (render() asks for ~25 fonts a frame).
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(os.path.join(FONT_DIR, name), int(size))


# --- Home Assistant helpers ------------------------------------------------
def _ha(method, path, body=None, **params):
    if not (HA_BASE_URL and HA_TOKEN):
        return None
    try:
        r = requests.request(
            method,
            f"{HA_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {HA_TOKEN}"},
            params=params or None,
            json=body,
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[ha] {method} {path} failed: {e}", flush=True)
        return None


def _local(iso):
    """Parse an ISO timestamp to local tz, or None."""
    try:
        return datetime.fromisoformat(iso).astimezone(TZINFO)
    except Exception:
        return None


def fetch_weather():
    """(condition, temp, feels) or (None, None, None)."""
    data = _ha("GET", f"/api/states/{HA_WEATHER_ENTITY}") if HA_WEATHER_ENTITY else None
    if not data:
        return None, None, None
    a = data.get("attributes", {})
    return data.get("state"), a.get("temperature"), a.get("apparent_temperature")


def fetch_forecast():
    """List of (label, condition, hi, lo) for the next days, or None."""
    if not HA_WEATHER_ENTITY:
        return None
    resp = _ha(
        "POST",
        "/api/services/weather/get_forecasts",
        {"entity_id": HA_WEATHER_ENTITY, "type": "daily"},
        return_response="true",
    )
    try:
        days = resp["service_response"][HA_WEATHER_ENTITY]["forecast"]
    except Exception:
        return None
    out = []
    for f in days[:FORECAST_DAYS]:
        dt = _local(f.get("datetime"))
        out.append((dt.strftime("%a") if dt else "", f.get("condition"),
                    f.get("temperature"), f.get("templow")))
    return out or None


def fetch_sun():
    """(sunrise_dt, sunset_dt) in local tz, or (None, None)."""
    data = _ha("GET", f"/api/states/{HA_SUN_ENTITY}") if HA_SUN_ENTITY else None
    if not data:
        return None, None
    a = data.get("attributes", {})
    return _local(a.get("next_rising")), _local(a.get("next_setting"))


def fetch_events():
    """List of (HH:MM-or-'all day', summary) for today, time-sorted, or None."""
    if not HA_CALENDAR_ENTITY:
        return None
    now = datetime.now(TZINFO)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    data = _ha(
        "GET",
        f"/api/calendars/{HA_CALENDAR_ENTITY}",
        start=start.isoformat(),
        end=(start + timedelta(days=1)).isoformat(),
    )
    if not data:
        return None
    out = []
    for ev in data:
        so = ev.get("start", {})
        summary = ev.get("summary", "(no title)")
        dt = _local(so.get("dateTime")) if "dateTime" in so else None
        if dt:
            out.append((dt, dt.strftime("%H:%M"), summary))
        else:
            out.append((start, "all day", summary))
    out.sort(key=lambda t: t[0])
    return [(lbl, s) for _, lbl, s in out[:MAX_EVENTS]]


# --- HA data cache: a background thread keeps render() free of network I/O --
# render() runs on every GET /dash.png (~once a minute); doing the four HA
# fetches there would block the response on serial network calls. Instead poll
# them in the background and have the widgets read this snapshot (rebound
# atomically, so a reader always sees one consistent dict).
HA_DATA = {"weather": (None, None, None), "forecast": None, "sun": (None, None), "events": None}


def ha_poll_loop():
    global HA_DATA
    while True:
        HA_DATA = {
            "weather": fetch_weather(),
            "forecast": fetch_forecast(),
            "sun": fetch_sun(),
            "events": fetch_events(),
        }
        time.sleep(DASH_POLL_MIN * 60)


def moon_phase(now):
    """Return (phase 0..1, illumination 0..1, name). Pure local synodic approx."""
    ref = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)  # a known new moon
    days = (now.astimezone(timezone.utc) - ref).total_seconds() / 86400.0
    phase = (days % 29.53058867) / 29.53058867
    illum = (1 - math.cos(2 * math.pi * phase)) / 2
    names = [
        "New", "Waxing crescent", "First quarter", "Waxing gibbous",
        "Full", "Waning gibbous", "Last quarter", "Waning crescent",
    ]
    return phase, illum, names[int(phase * 8 + 0.5) % 8]


# --- Claude usage: OAuth token refresh + usage fetch -----------------------
def read_usage():
    try:
        with open(USAGE_FILE) as f:
            d = json.load(f)
        stale = datetime.now(timezone.utc) - datetime.fromisoformat(d["updated"]) > timedelta(
            minutes=STALE_AFTER_MIN
        )
        return d, stale
    except Exception:
        return None, None


def _load_tokens():
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:
        return {"refresh_token": CLAUDE_REFRESH_TOKEN, "access_token": "", "expires_at": 0}


def _save_tokens(tok):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(tok, f)
    os.replace(tmp, TOKEN_FILE)


def _refresh_access(tok):
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": tok["refresh_token"],
        "client_id": CLAUDE_CLIENT_ID,
    }
    hdrs = {"User-Agent": CLAUDE_USER_AGENT}
    r = requests.post(CLAUDE_TOKEN_URL, json=payload, headers=hdrs, timeout=15)
    if r.status_code >= 400:  # some OAuth servers want form-encoding, not JSON
        r = requests.post(CLAUDE_TOKEN_URL, data=payload, headers=hdrs, timeout=15)
    r.raise_for_status()
    d = r.json()
    tok["access_token"] = d["access_token"]
    if d.get("refresh_token"):  # rotates — keep the new one or we lock ourselves out
        tok["refresh_token"] = d["refresh_token"]
    tok["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=int(d.get("expires_in", 3600)))
    ).timestamp()
    _save_tokens(tok)
    return tok


def _access_token():
    tok = _load_tokens()
    if not tok.get("refresh_token"):
        raise RuntimeError("no refresh token seeded (CLAUDE_REFRESH_TOKEN)")
    if not tok.get("access_token") or tok.get("expires_at", 0) < datetime.now(timezone.utc).timestamp() + 120:
        tok = _refresh_access(tok)
    return tok["access_token"]


def fetch_usage_once():
    def fmt(iso):
        if not iso:
            return ""
        try:
            return datetime.fromisoformat(iso).astimezone(TZINFO).strftime("%b %d, %H:%M")
        except Exception:
            return ""

    def get(token):
        return requests.get(
            CLAUDE_USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": CLAUDE_USER_AGENT,
            },
            timeout=15,
        )

    r = get(_access_token())
    if r.status_code == 401:
        r = get(_refresh_access(_load_tokens())["access_token"])
    r.raise_for_status()
    d = r.json()
    s, w, sn = d.get("five_hour") or {}, d.get("seven_day") or {}, d.get("seven_day_sonnet") or {}

    def pct(x):
        return round(x["utilization"]) if x.get("utilization") is not None else None

    return {
        "session_pct": pct(s), "session_reset": fmt(s.get("resets_at")),
        "week_pct": pct(w), "week_reset": fmt(w.get("resets_at")),
        "sonnet_pct": pct(sn), "sonnet_reset": fmt(sn.get("resets_at")),
        "updated": datetime.now(timezone.utc).isoformat(),
    }


def usage_poll_loop():
    while True:
        try:
            rec = fetch_usage_once()
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(USAGE_FILE, "w") as f:
                json.dump(rec, f)
            print(f"[usage] session={rec['session_pct']}% week={rec['week_pct']}%", flush=True)
        except Exception as e:
            print(f"[usage] fetch failed: {e}", flush=True)
        time.sleep(CLAUDE_POLL_MIN * 60)


# --- drawing primitives ----------------------------------------------------
def draw_weather_icon(dr, cx, cy, r, cond):
    """Filled grayscale weather glyph centred at (cx, cy), scale r, by condition."""
    c = (cond or "").lower()
    B = 0
    lw = max(2, int(r * 0.12))

    def cloud(ox, oy, s):
        dr.ellipse((ox - 1.7 * s, oy - 0.1 * s, ox - 0.1 * s, oy + 1.1 * s), fill=B)
        dr.ellipse((ox - 0.7 * s, oy - 0.8 * s, ox + 0.9 * s, oy + 0.9 * s), fill=B)
        dr.ellipse((ox + 0.1 * s, oy - 0.2 * s, ox + 1.7 * s, oy + 1.1 * s), fill=B)
        dr.rectangle((ox - 1.5 * s, oy + 0.4 * s, ox + 1.5 * s, oy + 1.1 * s), fill=B)

    def sun(ox, oy, rad):
        for k in range(8):
            a = k * math.pi / 4
            dr.line(
                (ox + math.cos(a) * rad * 1.25, oy + math.sin(a) * rad * 1.25,
                 ox + math.cos(a) * rad * 1.75, oy + math.sin(a) * rad * 1.75),
                fill=B, width=lw,
            )
        dr.ellipse((ox - rad, oy - rad, ox + rad, oy + rad), fill=B)

    def streaks(ox, oy, s, dots):
        for i in range(3):
            x = ox - 0.6 * s + i * 0.6 * s
            if dots:
                dr.ellipse((x - 0.09 * s, oy, x + 0.09 * s, oy + 0.18 * s), fill=B)
            else:
                dr.line((x, oy, x - 0.18 * s, oy + 0.7 * s), fill=B, width=lw)

    if "night" in c and "cloud" not in c and "rain" not in c:
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=B)
        dr.ellipse((cx - r + 0.5 * r, cy - r - 0.1 * r, cx + r + 0.6 * r, cy + r - 0.1 * r), fill=255)
    elif "sun" in c or "clear" in c:
        sun(cx, cy, r * 0.6)
    elif "partly" in c:
        sun(cx - 0.3 * r, cy - 0.35 * r, r * 0.42)
        cloud(cx + 0.2 * r, cy + 0.15 * r, r * 0.5)
    elif "rain" in c or "pour" in c or "drizzle" in c or "hail" in c:
        cloud(cx, cy - 0.25 * r, r * 0.55)
        streaks(cx, cy + 0.9 * r, r, dots=False)
    elif "snow" in c:
        cloud(cx, cy - 0.25 * r, r * 0.55)
        streaks(cx, cy + 0.95 * r, r, dots=True)
    elif "fog" in c or "mist" in c or "haz" in c:
        for i in range(4):
            yy = cy - 0.55 * r + i * 0.4 * r
            dr.line((cx - r, yy, cx + r, yy), fill=B, width=lw)
    elif "light" in c or "thunder" in c:
        cloud(cx, cy - 0.25 * r, r * 0.55)
        dr.polygon(
            [(cx, cy + 0.7 * r), (cx - 0.25 * r, cy + 1.4 * r), (cx, cy + 1.3 * r),
             (cx - 0.1 * r, cy + 1.9 * r), (cx + 0.3 * r, cy + 1.0 * r), (cx + 0.05 * r, cy + 1.1 * r)],
            fill=B,
        )
    else:
        cloud(cx, cy, r * 0.6)


def _trunc(d, s, font, avail):
    if d.textlength(s, font=font) <= avail:
        return s
    while s and d.textlength(s + "…", font=font) > avail:
        s = s[:-1]
    return s + "…"


# --- widgets: each draws inside box = (x, y, w, h) -------------------------
def w_clock(d, box):
    x, y, w, h = box
    now = datetime.now(TZINFO)
    d.text((x, y), now.strftime("%H:%M"), font=_font(True, h * 0.62), fill=0)
    d.text((x, y + h * 0.66), now.strftime("%a - %d/%m/%Y"), font=_font(False, h * 0.2), fill=0)


def w_weather(d, box):
    x, y, w, h = box
    cond, temp, feels = HA_DATA["weather"]
    r = h * 0.32
    cx, cy = x + r * 1.5, y + h * 0.42
    draw_weather_icon(d, cx, cy, r, cond if temp is not None else "cloudy")
    tx = cx + r + 16
    if temp is not None:
        d.text((tx, y), f"{round(temp)}°", font=_font(True, h * 0.6), fill=0)
        sub = cond or ""
        if feels is not None:
            sub = (sub + f"  feels {round(feels)}°").strip()
        d.text((tx, y + h * 0.62), sub, font=_font(False, h * 0.16), fill=0)
    else:
        d.text((tx, y + h * 0.3), "weather n/a", font=_font(False, h * 0.18), fill=0)


def w_forecast(d, box):
    x, y, w, h = box
    days = HA_DATA["forecast"]
    if not days:
        return
    cw = w / len(days)
    for i, (label, cond, hi, lo) in enumerate(days):
        cx = x + cw * (i + 0.5)
        d.text((cx - cw * 0.4, y), label, font=_font(True, h * 0.16), fill=0)
        draw_weather_icon(d, cx, y + h * 0.42, h * 0.16, cond)
        t = f"{round(hi)}°" if hi is not None else "—"
        if lo is not None:
            t += f"/{round(lo)}"
        d.text((cx - cw * 0.4, y + h * 0.74), t, font=_font(False, h * 0.16), fill=0)


def w_agenda(d, box):
    x, y, w, h = box
    d.text((x, y), "TODAY", font=_font(True, h * 0.14), fill=0)
    yy = y + h * 0.2
    events = HA_DATA["events"]
    f = _font(False, h * 0.13)
    if events is None:
        d.text((x, yy), "no calendar", font=f, fill=0)
        return
    if not events:
        d.text((x, yy), "nothing scheduled", font=f, fill=0)
        return
    tcol = w * 0.28
    for label, summary in events:
        d.text((x, yy), label, font=f, fill=0)
        d.text((x + tcol, yy), _trunc(d, summary, f, w - tcol), font=f, fill=0)
        yy += h * 0.17


def w_sunmoon(d, box):
    x, y, w, h = box
    rise, sett = HA_DATA["sun"]
    phase, illum, name = moon_phase(datetime.now(TZINFO))
    f = _font(False, h * 0.13)
    d.text((x, y), "SUN & MOON", font=_font(True, h * 0.13), fill=0)
    yy = y + h * 0.2
    d.text((x, yy), f"^ {rise.strftime('%H:%M')}" if rise else "^ --", font=f, fill=0)
    d.text((x + w * 0.45, yy), f"v {sett.strftime('%H:%M')}" if sett else "v --", font=f, fill=0)
    # moon glyph: disk + terminator showing the lit fraction
    mr = h * 0.22
    mcx, mcy = x + mr, y + h * 0.72
    d.ellipse((mcx - mr, mcy - mr, mcx + mr, mcy + mr), outline=0, width=3)
    if illum >= 0.98:
        d.ellipse((mcx - mr, mcy - mr, mcx + mr, mcy + mr), fill=0)
    elif illum > 0.02:
        lit_right = phase < 0.5
        d.chord((mcx - mr, mcy - mr, mcx + mr, mcy + mr), -90, 90 if lit_right else -90, fill=0)
        k = abs(2 * illum - 1) * mr
        d.ellipse((mcx - k, mcy - mr, mcx + k, mcy + mr), fill=0 if illum > 0.5 else 255)
    d.text((mcx + mr + 12, mcy - h * 0.12), name, font=f, fill=0)


def w_usage(d, box):
    x, y, w, h = box
    usage, stale = read_usage()
    d.text((x, y), "Claude usage" + ("  (stale)" if stale else ""), font=_font(True, h * 0.11), fill=0)
    yy = y + h * 0.16
    rows = [("Session", "session"), ("Week", "week"), ("Sonnet", "sonnet")]
    if not usage:
        d.text((x, yy), "usage n/a", font=_font(False, h * 0.11), fill=0)
        return
    f = _font(False, h * 0.1)
    bh = h * 0.1
    bx0, bx1 = x + w * 0.13, x + w * 0.48
    rh = (h - (yy - y)) / len(rows)
    for i, (name, key) in enumerate(rows):
        ry = yy + i * rh
        pct = usage.get(f"{key}_pct")
        d.text((x, ry), name, font=f, fill=0)
        d.rectangle((bx0, ry, bx1, ry + bh), outline=0, width=3)
        if pct is not None:
            d.rectangle((bx0, ry, bx0 + (bx1 - bx0) * max(0, min(1, pct / 100)), ry + bh), fill=0)
        txt = f"{pct}%" if pct is not None else "—"
        if usage.get(f"{key}_reset"):
            txt += f"  ·  resets {usage[f'{key}_reset']}"
        d.text((bx1 + 16, ry), txt, font=f, fill=0)


def render(rotate=0):
    W, H = KINDLE_W, KINDLE_H
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    pad = max(16, W // 42)

    # --- layout grid: each (widget, box) draws into its box; add/move/resize
    # here. Widgets are isolated — one that raises is logged and skipped, never
    # taking down the whole frame.
    hdr_h = H * 0.20
    mid_y, mid_b = H * 0.26, H * 0.60
    mid = W * 0.52
    rcol = W - mid - pad
    midrow = mid_b - mid_y
    layout = [
        (w_clock, (pad, pad, mid - pad, hdr_h)),
        (w_weather, (mid, pad, rcol, hdr_h)),
        (w_agenda, (pad, mid_y, mid - 2 * pad, midrow)),
        (w_forecast, (mid, mid_y, rcol, midrow * 0.45)),
        (w_sunmoon, (mid, mid_y + midrow * 0.5, rcol, midrow * 0.5)),
        (w_usage, (pad, mid_b + 2 * pad, W - 2 * pad, H - (mid_b + 2 * pad) - pad)),
    ]
    d.line((pad, H * 0.235, W - pad, H * 0.235), fill=0, width=2)
    d.line((pad, mid_b + pad, W - pad, mid_b + pad), fill=0, width=2)
    for fn, box in layout:
        try:
            fn(d, box)
        except Exception as e:
            print(f"[widget] {fn.__name__} failed: {e}", flush=True)

    if rotate in (90, 180, 270):
        img = img.rotate(rotate, expand=True)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path.startswith("/dash.png"):
            try:
                rotate = int(parse_qs(urlparse(self.path).query).get("rotate", ["0"])[0])
            except ValueError:
                rotate = 0
            try:
                png = render(rotate)
            except Exception as e:
                print(f"[render] failed: {e}", flush=True)
                self.send_response(500)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    print(f"kindle-dash on :8080  ({KINDLE_W}x{KINDLE_H}, tz={TZ})", flush=True)
    if HA_BASE_URL:
        threading.Thread(target=ha_poll_loop, daemon=True).start()
    if CLAUDE_REFRESH_TOKEN or os.path.exists(TOKEN_FILE):
        threading.Thread(target=usage_poll_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
