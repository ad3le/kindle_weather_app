#!/bin/sh
# Runs on the jailbroken Kindle 4: downloads today's weather image and shows it.
#
# The Kindle's own curl/wget are too old for GitHub's HTTPS, so this uses the
# lftp that ships with the USBNetwork package. Certificate checking is off
# because the Kindle's list of trusted certificates is just as outdated; the
# download is still encrypted, and it is only a weather picture.

URL="https://ad3le.github.io/kindle_weather_app/weather.png"
FILE="/tmp/weather.png"
LFTP="/mnt/us/usbnet/bin/lftp"

# Try for about two minutes, in case Wi-Fi is still reconnecting.
n=0
while [ $n -lt 6 ]; do
    rm -f "$FILE.new"
    if "$LFTP" -c "set ssl:verify-certificate no; set net:timeout 20; set net:max-retries 1; get $URL -o $FILE.new" \
        && [ -s "$FILE.new" ]; then
        mv "$FILE.new" "$FILE"
        eips -c            # clear the screen
        eips -c            # twice, to remove e-ink ghosting
        eips -g "$FILE"    # draw the image
        exit 0
    fi
    n=$((n + 1))
    sleep 20
done
exit 1
