# /root/.bash_profile
# Executed for the root login shell in the Nightmare Loader live environment.
# On tty1 the graphical Nightmare PE desktop is started automatically via
# startx.  On other ttys (SSH, serial, etc.) the text welcome banner is shown
# instead so those sessions remain useful without an X display.

# Source system-wide profile first (sets PATH etc.)
[ -f /etc/profile ] && . /etc/profile

# Auto-start the graphical desktop on tty1 when X is available and not yet
# running.  The intentional absence of 'exec' means that if X fails to start
# or the session exits cleanly, the shell falls through to the text welcome
# banner below rather than triggering an infinite respawn loop via getty.
if [[ "$(tty)" == /dev/tty1 ]] && [[ -z "${DISPLAY:-}" ]] && command -v startx >/dev/null 2>&1; then
    startx -- :0 vt1 2>/tmp/nightmare-x-startup.log || true
fi

# Always show the text welcome banner – on non-graphical ttys it is the
# primary UI; on tty1 it serves as a fallback if X failed to start.
[ -x /usr/local/bin/nightmare-welcome.sh ] && /usr/local/bin/nightmare-welcome.sh
