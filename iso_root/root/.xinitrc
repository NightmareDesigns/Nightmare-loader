#!/bin/bash
# /root/.xinitrc
# Nightmare Loader PE – X session initialisation script.
#
# Invoked by startx / xinit after the X server has started.
# Sequence:
#   1. Apply display and input settings
#   2. Paint the solid black background
#   3. Launch the Nightmare Loader web-UI server in the background
#   4. Start the tint2 panel
#   5. Wait for the web server to be ready, then open Chromium in app-mode
#   6. Hand off to openbox (the session ends when openbox exits)

# ── Display settings ────────────────────────────────────────────────────────

# Disable DPMS screen blanking / power saving in the live session
xset s off -dpms 2>/dev/null || true

# Solid near-black background (avoids the ugly grey X default)
xsetroot -solid '#0a0000' 2>/dev/null || true

# ── Tint2 panel ─────────────────────────────────────────────────────────────
tint2 &

# ── Nightmare Loader web-UI server ──────────────────────────────────────────
# Start the server without auto-opening a browser (we will open Chromium
# below once the server is confirmed to be ready).
nightmare-loader ui --no-browser &
_NL_PID=$!

# Ensure the background server is terminated when the X session (openbox) exits.
trap 'kill "$_NL_PID" 2>/dev/null || true' EXIT

# ── Wait for server, then open the browser ──────────────────────────────────
(
    _PORT=8321
    _SERVER_READY=0
    for _i in $(seq 1 40); do
        if curl -sf "http://127.0.0.1:${_PORT}/" >/dev/null 2>&1; then
            _SERVER_READY=1
            break
        fi
        sleep 0.5
    done

    if [[ "$_SERVER_READY" -ne 1 ]]; then
        _MSG="Nightmare Loader UI did not become ready on http://127.0.0.1:${_PORT}/ after waiting."
        printf '%s\n' "$_MSG" >> /tmp/nightmare-loader-ui.log
        if command -v xterm >/dev/null 2>&1; then
            xterm -T "Nightmare Loader – startup failure" \
                  -e sh -c "printf '%s\n' \"$_MSG\"; printf 'See /tmp/nightmare-loader-ui.log\n'; printf 'Press Enter to close...\n'; read _" &
        fi
        exit 0
    fi

    # Determine the available Chromium binary name
    _BROWSER=""
    for _b in chromium chromium-browser google-chrome google-chrome-stable; do
        if command -v "$_b" >/dev/null 2>&1; then
            _BROWSER="$_b"
            break
        fi
    done

    if [[ -n "$_BROWSER" ]]; then
        # --no-sandbox is required because this live session runs as root;
        # Chromium refuses to start with the sandbox enabled under root.
        "$_BROWSER" \
            --no-sandbox \
            --disable-infobars \
            --no-first-run \
            --disable-translate \
            --disable-features=TranslateUI \
            --app="http://127.0.0.1:${_PORT}" &
    else
        # Fallback: try xdg-open if no Chromium binary is found
        xdg-open "http://127.0.0.1:${_PORT}" 2>/dev/null || true
    fi
) &

# ── Window manager ──────────────────────────────────────────────────────────
# exec replaces this script so X exits cleanly when openbox quits.
exec openbox --config-file /root/.config/openbox/rc.xml
