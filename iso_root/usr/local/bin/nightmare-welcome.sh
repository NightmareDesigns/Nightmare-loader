#!/bin/bash
# nightmare-welcome.sh
# Auto-run welcome screen for the Nightmare Loader live environment.
# Sourced from /root/.bash_profile on first login so the user lands here
# immediately after the branded GRUB preloader finishes booting.

# Only show the welcome screen on the physical console (tty1/tty2), not over
# SSH or in a nested terminal.  This avoids cluttering remote sessions.
if [[ "$(tty)" != /dev/tty[12] ]]; then
    return 0 2>/dev/null || exit 0
fi

# Colour codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

clear

echo -e "${RED}${BOLD}"
cat <<'BANNER'
 _   _ _       _     _                            _                     _
| \ | (_) __ _| |__ | |_ _ __ ___   __ _ _ __ ___| |     ___   __ _  __| | ___ _ __
|  \| | |/ _` | '_ \| __| '_ ` _ \ / _` | '__/ _ \ |    / _ \ / _` |/ _` |/ _ \ '__|
| |\  | | (_| | | | | |_| | | | | | (_| | | |  __/ |___| (_) | (_| | (_| |  __/ |
|_| \_|_|\__, |_| |_|\__|_| |_| |_|\__,_|_|  \___|______\___/ \__,_|\__,_|\___|_|
          |___/
BANNER
echo -e "${RESET}"

echo -e "${GREEN}${BOLD}  LIVE ENVIRONMENT  ·  UEFI + Legacy BIOS  ·  Multi-ISO USB Creator${RESET}"
echo -e "${DIM}  ──────────────────────────────────────────────────────────────────${RESET}"
echo
echo -e "  ${BOLD}Quick start${RESET}"
echo
echo -e "  ${GREEN}1.${RESET}  Find your USB drive:"
echo -e "       ${BOLD}nightmare-loader drives${RESET}"
echo
echo -e "  ${GREEN}2.${RESET}  Prepare the drive  ${RED}⚠ erases all data ⚠${RESET}"
echo -e "       ${BOLD}nightmare-loader prepare /dev/sdX${RESET}"
echo
echo -e "  ${GREEN}3.${RESET}  Add ISO images:"
echo -e "       ${BOLD}nightmare-loader add /dev/sdX /path/to/ubuntu.iso${RESET}"
echo -e "       ${BOLD}nightmare-loader add /dev/sdX /path/to/arch.iso${RESET}"
echo
echo -e "  ${GREEN}4.${RESET}  Or use the web UI (open the printed URL in any browser):"
echo -e "       ${BOLD}nightmare-loader ui${RESET}"
echo
echo -e "  ${DIM}Run  nightmare-loader --help  for the full command reference.${RESET}"
echo -e "  ${DIM}ISOs on this machine are at /opt/nightmare-loader if you need them.${RESET}"
echo
echo -e "${DIM}  ──────────────────────────────────────────────────────────────────${RESET}"
echo
