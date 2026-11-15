#!/bin/sh
# Weather display for a jailbroken Kindle 4 (non-touch) running on battery.
#
#   sh weather.sh once   download and show the image once, then exit
#   sh weather.sh test   two short cycles (show, sleep 3 min, wake), then
#                        hand the Kindle back to its normal interface
#   sh weather.sh        run as the display: show the image, sleep until the
#                        next morning, wake up, repeat
#
# As a display it switches off the Kindle's normal interface (so the status
# bar and screensaver do not draw over the picture) and its power manager
# (so this script decides when to sleep). Restarting the Kindle undoes both.
# Pressing the power button while it sleeps wakes it, refreshes the picture
# and leaves a few minutes to log in over SSH.

URL="https://ad3le.github.io/kindle_weather_app/weather.png"
REFRESH_HOUR=4      # daily refresh time in UTC, the Kindle's clock:
REFRESH_MIN=30      # 04:30 UTC = 05:30 in winter / 06:30 in summer in Leipzig
AWAKE=180           # seconds to stay awake after a refresh
RETRY=3600          # seconds to sleep if the download failed

DIR="/mnt/us/weather"
FILE="/tmp/weather.png"
LOG="$DIR/log.txt"
# The Kindle's own curl/wget are too old for GitHub's HTTPS; USBNetwork's lftp
# is not. Certificate checking is off because the Kindle's trusted
# certificates are just as outdated. It is only a weather picture.
LFTP="/mnt/us/usbnet/bin/lftp"
RTC="/sys/devices/platform/mxc_rtc.0/wakeup_enable"

MODE="${1:-daily}"
trap '' HUP

log() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"
}

battery() {
    gasgauge-info -c 2>/dev/null || echo "?"
}

wait_for_wifi() {
    lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
    n=0
    while [ $n -lt 45 ]; do
        [ "$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null)" = "CONNECTED" ] && return 0
        n=$((n + 1))
        sleep 2
    done
    return 1
}

show_weather() {
    n=0
    while [ $n -lt 3 ]; do
        rm -f "$FILE.new"
        if "$LFTP" -c "set ssl:verify-certificate no; set net:timeout 20; set net:max-retries 1; get $URL -o $FILE.new" \
            >/dev/null 2>&1 && [ -s "$FILE.new" ]; then
            mv "$FILE.new" "$FILE"
            eips -c            # clear the screen
            eips -c            # twice, to remove e-ink ghosting
            eips -g "$FILE"    # draw the image
            return 0
        fi
        n=$((n + 1))
        sleep 10
    done
    return 1
}

seconds_until_refresh() {
    now=$(date -u +%s)
    wait=$((REFRESH_HOUR * 3600 + REFRESH_MIN * 60 - now % 86400))
    # Less than 10 minutes away counts as "already done": aim for tomorrow.
    [ $wait -lt 600 ] && wait=$((wait + 86400))
    echo $wait
}

sleep_for() {
    lipc-set-prop com.lab126.cmd wirelessEnable 0 2>/dev/null
    sleep 3
    sync
    echo "$1" > "$RTC"
    echo mem > /sys/power/state    # returns when the Kindle wakes up again
    sleep 5
}

mkdir -p "$DIR"

if [ "$MODE" = "once" ]; then
    wait_for_wifi && show_weather
    exit $?
fi

log "started ($MODE), battery $(battery)"
/etc/init.d/framework stop >/dev/null 2>&1
/etc/init.d/powerd stop >/dev/null 2>&1
sleep 5

cycle=0
while true; do
    cycle=$((cycle + 1))
    if wait_for_wifi; then
        if show_weather; then
            log "shown, battery $(battery)"
            pause=$(seconds_until_refresh)
        else
            log "download failed"
            pause=$RETRY
        fi
    else
        log "no Wi-Fi"
        pause=$RETRY
    fi

    if [ "$MODE" = "test" ]; then
        if [ $cycle -ge 3 ]; then
            log "test finished"
            /etc/init.d/powerd start >/dev/null 2>&1
            /etc/init.d/framework start >/dev/null 2>&1
            exit 0
        fi
        sleep 30
        pause=180
    else
        sleep $AWAKE
        # The awake time may have carried us past the refresh time.
        [ $pause -ne $RETRY ] && pause=$(seconds_until_refresh)
    fi

    # Keep the log short.
    tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"

    log "sleeping $pause s"
    sleep_for $pause
    log "woke up"
done
