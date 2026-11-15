#!/bin/sh
# Runs on the jailbroken Kindle: downloads today's weather image and shows it.
# NOT yet tested on a real device - paths and tools differ between Kindle models.

URL="https://ad3le.github.io/kindle_weather_app/weather.png"
FILE="/tmp/weather.png"

# Wait up to a minute for Wi-Fi after waking up.
n=0
while [ $n -lt 12 ]; do
    ping -c 1 -W 5 ad3le.github.io >/dev/null 2>&1 && break
    n=$((n + 1))
    sleep 5
done

if curl -fsSL -o "$FILE.new" "$URL" 2>/dev/null || wget -q -O "$FILE.new" "$URL"; then
    mv "$FILE.new" "$FILE"
    eips -c            # clear the screen
    eips -c            # twice, to remove e-ink ghosting
    eips -g "$FILE"    # draw the image
fi
