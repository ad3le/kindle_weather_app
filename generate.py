#!/usr/bin/env python3
"""Render a daily weather report as a grayscale PNG for a Kindle e-ink screen.

Fetches the forecast from Open-Meteo (free, no API key) and draws:
  - today's weather in the morning, at noon and in the evening
  - tomorrow's average

Usage:
  python generate.py                      # live data -> site/weather.png
  python generate.py --sample             # built-in sample data (no network)
  python generate.py --width 758 --height 1024 --out site/weather.png
"""
import argparse
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# ---- Settings -------------------------------------------------------------

LOCATION_NAME = "Leipzig"
LATITUDE = 51.3397
LONGITUDE = 12.3731
TIMEZONE = "Europe/Berlin"

# Hours of the day shown for today (24h clock, local time).
DAY_PARTS = [("Morning", 8), ("Noon", 13), ("Evening", 19)]

BLACK, DARK, MID, LIGHT, WHITE = 0, 70, 130, 200, 255

FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/Library/Fonts",
]

# ---- Weather codes (WMO) --------------------------------------------------

WMO = {
    0: ("Clear", "sun"),
    1: ("Mostly clear", "sun"),
    2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloud"),
    45: ("Fog", "fog"),
    48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "rain"),
    53: ("Drizzle", "rain"),
    55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"),
    57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"),
    67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Light showers", "rain"),
    81: ("Showers", "rain"),
    82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"),
    86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "thunder"),
    96: ("Thunderstorm, hail", "thunder"),
    99: ("Thunderstorm, hail", "thunder"),
}


def describe(code):
    return WMO.get(int(code), ("Unknown", "cloud"))


# ---- Data -----------------------------------------------------------------


def fetch_forecast():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": TIMEZONE,
        "forecast_days": 2,
        "wind_speed_unit": "kmh",
        "hourly": "temperature_2m,weather_code,precipitation_probability,wind_speed_10m",
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,"
        "weather_code,precipitation_probability_max",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def sample_forecast():
    """Made-up data in the same shape as the API response, for layout testing."""
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    tomorrow = today.fromordinal(today.toordinal() + 1)
    times, temps, codes, rain, wind = [], [], [], [], []
    for day in (today, tomorrow):
        for hour in range(24):
            times.append(f"{day.isoformat()}T{hour:02d}:00")
            temps.append(round(6 + 5 * math.sin((hour - 9) / 24 * 2 * math.pi), 1))
            codes.append(3 if hour < 10 else (2 if hour < 16 else 61))
            rain.append(10 if hour < 16 else 70)
            wind.append(12 + hour % 7)
    return {
        "hourly": {
            "time": times,
            "temperature_2m": temps,
            "weather_code": codes,
            "precipitation_probability": rain,
            "wind_speed_10m": wind,
        },
        "daily": {
            "time": [today.isoformat(), tomorrow.isoformat()],
            "temperature_2m_mean": [6.1, 4.3],
            "temperature_2m_max": [11.0, 7.8],
            "temperature_2m_min": [1.2, -0.6],
            "weather_code": [61, 71],
            "precipitation_probability_max": [70, 45],
        },
    }


def summarise(data):
    """Pick out the values the dashboard shows."""
    hourly, daily = data["hourly"], data["daily"]
    today = daily["time"][0]
    index = {t: i for i, t in enumerate(hourly["time"])}

    parts = []
    for label, hour in DAY_PARTS:
        i = index[f"{today}T{hour:02d}:00"]
        parts.append(
            {
                "label": label,
                "hour": hour,
                "temp": hourly["temperature_2m"][i],
                "code": hourly["weather_code"][i],
                "rain": hourly["precipitation_probability"][i],
                "wind": hourly["wind_speed_10m"][i],
            }
        )

    return {
        "today": datetime.fromisoformat(today),
        "today_min": daily["temperature_2m_min"][0],
        "today_max": daily["temperature_2m_max"][0],
        "parts": parts,
        "tomorrow": {
            "date": datetime.fromisoformat(daily["time"][1]),
            "mean": daily["temperature_2m_mean"][1],
            "min": daily["temperature_2m_min"][1],
            "max": daily["temperature_2m_max"][1],
            "code": daily["weather_code"][1],
            "rain": daily["precipitation_probability_max"][1],
        },
    }


# ---- Drawing --------------------------------------------------------------


def load_font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for directory in FONT_DIRS:
        path = os.path.join(directory, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def fit_font(d, text, size, max_width):
    """Largest font up to `size` at which `text` fits in `max_width`."""
    while size > 8 and d.textlength(text, font=load_font(size)) > max_width:
        size -= 1
    return load_font(size)


def temp_text(value):
    rounded = round(value)
    if rounded == 0:
        rounded = 0  # avoid "-0"
    return f"{rounded}°".replace("-", "−")


def value_or_dash(value, suffix):
    return "–" if value is None else f"{round(value)}{suffix}"


def draw_cloud(d, cx, cy, r, fill=WHITE, outline=BLACK, width=3):
    """A cloud roughly 2.4r wide centred on (cx, cy)."""
    blobs = [
        (cx - 0.65 * r, cy + 0.15 * r, 0.50 * r),
        (cx - 0.15 * r, cy - 0.25 * r, 0.62 * r),
        (cx + 0.55 * r, cy + 0.05 * r, 0.55 * r),
    ]
    base = (cx - 1.1 * r, cy + 0.15 * r, cx + 1.1 * r, cy + 0.65 * r)
    # Outline pass slightly larger, then fill pass, so the shapes merge cleanly.
    for x, y, rad in blobs:
        rad += width
        d.ellipse((x - rad, y - rad, x + rad, y + rad), fill=outline)
    d.rounded_rectangle(
        (base[0] - width, base[1] - width, base[2] + width, base[3] + width),
        radius=0.25 * r + width,
        fill=outline,
    )
    for x, y, rad in blobs:
        d.ellipse((x - rad, y - rad, x + rad, y + rad), fill=fill)
    d.rounded_rectangle(base, radius=0.25 * r, fill=fill)


def draw_sun(d, cx, cy, r, width=3):
    for k in range(8):
        a = k * math.pi / 4
        d.line(
            (
                cx + 1.35 * r * math.cos(a),
                cy + 1.35 * r * math.sin(a),
                cx + 1.9 * r * math.cos(a),
                cy + 1.9 * r * math.sin(a),
            ),
            fill=BLACK,
            width=width,
        )
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE, outline=BLACK, width=width)


def draw_icon(d, kind, cx, cy, size):
    """Draw a weather icon inside a square of `size` centred on (cx, cy)."""
    u = size / 2
    w = max(2, round(size / 26))
    if kind == "sun":
        draw_sun(d, cx, cy, 0.42 * u, w)
    elif kind == "partly":
        draw_sun(d, cx + 0.32 * u, cy - 0.30 * u, 0.30 * u, w)
        draw_cloud(d, cx - 0.10 * u, cy + 0.20 * u, 0.62 * u, width=w)
    elif kind == "cloud":
        draw_cloud(d, cx, cy, 0.75 * u, width=w)
    elif kind == "fog":
        draw_cloud(d, cx, cy - 0.30 * u, 0.62 * u, width=w)
        for k in range(3):
            y = cy + (0.35 + 0.25 * k) * u
            d.line((cx - 0.75 * u, y, cx + 0.75 * u, y), fill=DARK, width=w)
    elif kind == "rain":
        draw_cloud(d, cx, cy - 0.25 * u, 0.68 * u, width=w)
        for k in (-1, 0, 1):
            x = cx + k * 0.42 * u
            d.line((x + 0.08 * u, cy + 0.42 * u, x - 0.12 * u, cy + 0.88 * u), fill=BLACK, width=w)
    elif kind == "snow":
        draw_cloud(d, cx, cy - 0.25 * u, 0.68 * u, width=w)
        for k in (-1, 0, 1):
            x, y, s = cx + k * 0.42 * u, cy + 0.66 * u, 0.13 * u
            for a in (0, math.pi / 3, 2 * math.pi / 3):
                d.line(
                    (x - s * math.cos(a), y - s * math.sin(a), x + s * math.cos(a), y + s * math.sin(a)),
                    fill=BLACK,
                    width=max(2, w - 1),
                )
    elif kind == "thunder":
        draw_cloud(d, cx, cy - 0.25 * u, 0.68 * u, width=w)
        bolt = [
            (cx + 0.10 * u, cy + 0.30 * u),
            (cx - 0.22 * u, cy + 0.68 * u),
            (cx - 0.02 * u, cy + 0.68 * u),
            (cx - 0.14 * u, cy + 1.00 * u),
            (cx + 0.26 * u, cy + 0.56 * u),
            (cx + 0.06 * u, cy + 0.56 * u),
            (cx + 0.24 * u, cy + 0.30 * u),
        ]
        d.polygon(bolt, fill=BLACK)


def render(summary, width, height, updated):
    s = width / 600  # layout is designed at 600 px wide and scaled from there
    px = lambda v: round(v * s)
    img = Image.new("L", (width, height), WHITE)
    d = ImageDraw.Draw(img)
    margin = px(36)

    # Header
    d.text((margin, px(30)), LOCATION_NAME, font=load_font(px(54), bold=True), fill=BLACK)
    date_line = f"{summary['today']:%A}, {summary['today'].day} {summary['today']:%B}"
    d.text((margin, px(98)), date_line, font=load_font(px(24)), fill=DARK)
    range_line = f"{temp_text(summary['today_min'])} / {temp_text(summary['today_max'])}"
    d.text((width - margin, px(52)), range_line, font=load_font(px(30)), fill=BLACK, anchor="ra")
    d.text((width - margin, px(98)), "low / high", font=load_font(px(20)), fill=MID, anchor="ra")
    d.line((margin, px(144), width - margin, px(144)), fill=BLACK, width=px(3))

    # Space left for the three day parts and the "tomorrow" panel
    top = px(144)
    footer_h = px(44)
    tomorrow_h = px(190)
    rows_bottom = height - footer_h - tomorrow_h
    row_h = (rows_bottom - top) / len(summary["parts"])

    for n, part in enumerate(summary["parts"]):
        y0 = top + n * row_h
        mid = y0 + row_h / 2
        text, icon = describe(part["code"])
        d.text((margin, mid - px(32)), part["label"], font=load_font(px(26), bold=True), fill=BLACK)
        d.text((margin, mid + px(6)), f"{part['hour']:02d}:00", font=load_font(px(22)), fill=MID)
        draw_icon(d, icon, px(218), mid, px(84))
        d.text((px(408), mid), temp_text(part["temp"]), font=load_font(px(54), bold=True), fill=BLACK, anchor="rm")
        right, room = width - margin, px(140)
        d.text((right, mid - px(34)), text, font=fit_font(d, text, px(21), room), fill=BLACK, anchor="ra")
        detail = f"Rain {value_or_dash(part['rain'], '%')}"
        d.text((right, mid - px(4)), detail, font=load_font(px(19)), fill=DARK, anchor="ra")
        detail = f"Wind {value_or_dash(part['wind'], ' km/h')}"
        d.text((right, mid + px(22)), detail, font=load_font(px(19)), fill=DARK, anchor="ra")
        if n:
            d.line((margin, y0, width - margin, y0), fill=LIGHT, width=px(2))

    # Tomorrow
    t = summary["tomorrow"]
    y0 = rows_bottom
    d.rectangle((0, y0, width, y0 + tomorrow_h), fill=BLACK)
    mid = y0 + tomorrow_h / 2
    text, icon = describe(t["code"])
    d.text((margin, y0 + px(22)), "Tomorrow", font=load_font(px(30), bold=True), fill=WHITE)
    d.text((margin, y0 + px(62)), f"{t['date']:%A}", font=load_font(px(22)), fill=LIGHT)
    d.text((margin, y0 + px(108)), "average", font=load_font(px(20)), fill=LIGHT)
    d.text((margin, y0 + px(134)), text, font=fit_font(d, text, px(22), px(190)), fill=WHITE)
    # Icon sits on a white disc so it stays readable on the black panel.
    r = px(62)
    d.ellipse((px(300) - r, mid - r, px(300) + r, mid + r), fill=WHITE)
    draw_icon(d, icon, px(300), mid, px(84))
    d.text((width - margin, y0 + px(22)), temp_text(t["mean"]), font=load_font(px(64), bold=True), fill=WHITE, anchor="ra")
    low_high = f"{temp_text(t['min'])} / {temp_text(t['max'])}"
    d.text((width - margin, y0 + px(104)), low_high, font=load_font(px(22)), fill=LIGHT, anchor="ra")
    d.text((width - margin, y0 + px(134)), f"Rain {value_or_dash(t['rain'], '%')}", font=load_font(px(22)), fill=LIGHT, anchor="ra")

    # Footer
    footer = f"Updated {updated:%H:%M} · open-meteo.com"
    d.text((width / 2, height - footer_h / 2), footer, font=load_font(px(18)), fill=MID, anchor="mm")
    return img


def render_landscape(summary, width, height, updated):
    """Same content as render(), laid out for a screen that is wider than tall."""
    s = width / 800  # designed at 800 px wide and scaled from there
    px = lambda v: round(v * s)
    img = Image.new("L", (width, height), WHITE)
    d = ImageDraw.Draw(img)
    margin = px(36)

    # Header
    d.text((margin, px(18)), LOCATION_NAME, font=load_font(px(48), bold=True), fill=BLACK)
    date_line = f"{summary['today']:%A}, {summary['today'].day} {summary['today']:%B}"
    d.text((margin, px(78)), date_line, font=load_font(px(22)), fill=DARK)
    range_line = f"{temp_text(summary['today_min'])} / {temp_text(summary['today_max'])}"
    d.text((width - margin, px(34)), range_line, font=load_font(px(30)), fill=BLACK, anchor="ra")
    d.text((width - margin, px(78)), "low / high", font=load_font(px(20)), fill=MID, anchor="ra")
    d.line((margin, px(118), width - margin, px(118)), fill=BLACK, width=px(3))

    # Three columns: morning, noon, evening
    footer_h = px(36)
    tomorrow_h = px(150)
    band_top = height - footer_h - tomorrow_h
    top = px(118)
    col_w = (width - 2 * margin) / len(summary["parts"])
    step = (band_top - top) / 298  # vertical positions below assume 298 px of room
    at = lambda v: top + v * step
    for n, part in enumerate(summary["parts"]):
        cx = margin + col_w * (n + 0.5)
        room = col_w - px(24)
        text, icon = describe(part["code"])
        d.text((cx, at(34)), part["label"], font=load_font(px(26), bold=True), fill=BLACK, anchor="mm")
        d.text((cx, at(64)), f"{part['hour']:02d}:00", font=load_font(px(19)), fill=MID, anchor="mm")
        draw_icon(d, icon, cx, at(122), px(84))
        d.text((cx, at(198)), temp_text(part["temp"]), font=load_font(px(56), bold=True), fill=BLACK, anchor="mm")
        d.text((cx, at(244)), text, font=fit_font(d, text, px(21), room), fill=BLACK, anchor="mm")
        detail = f"Rain {value_or_dash(part['rain'], '%')} · Wind {value_or_dash(part['wind'], ' km/h')}"
        d.text((cx, at(274)), detail, font=fit_font(d, detail, px(17), room), fill=DARK, anchor="mm")
        if n:
            x = margin + col_w * n
            d.line((x, at(20), x, at(284)), fill=LIGHT, width=px(2))

    # Tomorrow
    t = summary["tomorrow"]
    y0 = band_top
    d.rectangle((0, y0, width, y0 + tomorrow_h), fill=BLACK)
    mid = y0 + tomorrow_h / 2
    text, icon = describe(t["code"])
    d.text((margin, y0 + px(18)), "Tomorrow", font=load_font(px(30), bold=True), fill=WHITE)
    d.text((margin, y0 + px(62)), f"{t['date']:%A} · average", font=load_font(px(20)), fill=LIGHT)
    d.text((margin, y0 + px(100)), text, font=fit_font(d, text, px(22), px(280)), fill=WHITE)
    r = px(56)
    d.ellipse((width / 2 - r, mid - r, width / 2 + r, mid + r), fill=WHITE)
    draw_icon(d, icon, width / 2, mid, px(76))
    d.text((width - margin, y0 + px(14)), temp_text(t["mean"]), font=load_font(px(62), bold=True), fill=WHITE, anchor="ra")
    detail = f"{temp_text(t['min'])} / {temp_text(t['max'])} · Rain {value_or_dash(t['rain'], '%')}"
    d.text((width - margin, y0 + px(100)), detail, font=load_font(px(21)), fill=LIGHT, anchor="ra")

    # Footer
    footer = f"Updated {updated:%H:%M} · open-meteo.com"
    d.text((width / 2, height - footer_h / 2), footer, font=load_font(px(16)), fill=MID, anchor="mm")
    return img


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--width", type=int, default=int(os.environ.get("KINDLE_WIDTH", 600)))
    parser.add_argument("--height", type=int, default=int(os.environ.get("KINDLE_HEIGHT", 800)))
    parser.add_argument("--out", default="site/weather.png")
    parser.add_argument(
        "--orientation",
        choices=["portrait", "landscape-left", "landscape-right"],
        default=os.environ.get("KINDLE_ORIENTATION", "portrait"),
        help="landscape-left: Kindle turned so its buttons are on the left; "
        "landscape-right: buttons on the right",
    )
    parser.add_argument("--sample", action="store_true", help="use built-in sample data instead of the API")
    args = parser.parse_args()

    data = sample_forecast() if args.sample else fetch_forecast()
    summary, now = summarise(data), datetime.now(ZoneInfo(TIMEZONE))
    if args.orientation == "portrait":
        image = upright = render(summary, args.width, args.height, now)
    else:
        # Draw wide, then turn it: the Kindle screen itself is always portrait.
        upright = render_landscape(summary, args.height, args.width, now)
        image = upright.rotate(90 if args.orientation == "landscape-left" else -90, expand=True)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # 8-bit grayscale, non-interlaced: the format the Kindle's `eips` tool expects.
    image.save(args.out, format="PNG", optimize=True)
    # An upright copy for looking at in a browser.
    upright.save(os.path.join(os.path.dirname(args.out) or ".", "preview.png"), format="PNG", optimize=True)
    print(f"Wrote {args.out} ({args.width}x{args.height}, {args.orientation})")


if __name__ == "__main__":
    main()
