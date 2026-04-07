# /root/.bash_profile
# Executed for the root login shell in the Nightmare Loader live environment.
# Runs the welcome screen automatically so the user lands on the branded
# prompt immediately after the GRUB preloader finishes booting.

# Source system-wide profile first (sets PATH etc.)
[ -f /etc/profile ] && . /etc/profile

# Show the Nightmare Loader welcome banner
[ -x /usr/local/bin/nightmare-welcome.sh ] && /usr/local/bin/nightmare-welcome.sh
