# Kindle weather dashboard

A daily weather report for Leipzig, drawn as an image for an old Kindle's e-ink screen.

It shows today's weather in the morning (08:00), at noon (13:00) and in the evening (19:00),
plus tomorrow's average.

## How it works

1. A GitHub Action (`.github/workflows/weather.yml`) runs once a day, early in the morning.
2. `generate.py` fetches the forecast from [Open-Meteo](https://open-meteo.com) (free, no API key)
   and draws a grayscale PNG the size of the Kindle screen.
3. The image is published with GitHub Pages at
   `https://ad3le.github.io/kindle_weather_app/weather.png`.
4. The jailbroken Kindle downloads that image once a day and displays it (`kindle/weather.sh`).

## One-time setup on GitHub

In the repository: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Changing things

| What | Where |
| --- | --- |
| Portrait or landscape | `KINDLE_ORIENTATION` in `.github/workflows/weather.yml` |
| Screen size | `KINDLE_WIDTH` / `KINDLE_HEIGHT` in `.github/workflows/weather.yml` |
| Time of the daily update | `cron` in `.github/workflows/weather.yml` (UTC) |
| Location, hours shown | Settings at the top of `generate.py` |

## Trying it locally

```bash
pip install -r requirements.txt
python generate.py            # live forecast -> site/weather.png
python generate.py --sample   # made-up data, no network needed
```
