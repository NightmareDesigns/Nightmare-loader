# /root/.bash_profile
# Executed for the root login shell in the Nightmare Loader live environment.
# On tty1 the graphical Nightmare PE desktop is started automatically via
# startx.  On other ttys (SSH, serial, etc.) the text welcome banner is shown
# instead so those sessions remain useful without an X display.

# Source system-wide profile first (sets PATH etc.)
[ -f /etc/profile ] && . /etc/profile

# Auto-start the graphical desktop on tty1 when X is available and not yet
# running.  'exec' replaces this shell so that when the X session ends the
# getty respawns and offers a fresh login rather than leaving a stale shell.
if [[ "$(tty)" == /dev/tty1 ]] && [[ -z "${DISPLAY:-}" ]] && command -v startx >/dev/null 2>&1; then
    exec startx -- :0 vt1 2>/tmp/nightmare-x-startup.log
fi

# Fallback for non-graphical sessions: show the text welcome banner.
[ -x /usr/local/bin/nightmare-welcome.sh ] && /usr/local/bin/nightmare-welcome.sh
