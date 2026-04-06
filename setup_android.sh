#!/data/data/com.termux/files/usr/bin/bash
# setup_android.sh
# One-shot Termux setup script for Nightmare Loader on Android.
#
# Requirements:
#   - Termux (https://github.com/termux/termux-app) installed from F-Droid
#     or GitHub Releases (NOT the Google Play version – it is outdated).
#   - Run this script inside a Termux session.
#
# What this script does:
#   1. Updates Termux packages
#   2. Installs Python 3, pip, and disk-utility dependencies
#   3. Installs Nightmare Loader from the local checkout (or from PyPI)
#   4. Creates a Termux:Widget launcher shortcut in ~/.shortcuts/
#
# For full USB drive partitioning support you also need:
#   - A rooted Android device
#   - Termux:Widget add-on (from F-Droid) to use the home-screen shortcut

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RESET='\033[0m'

info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
step()  { echo -e "\n${BOLD}$*${RESET}"; }

step "============================================================"
step " Nightmare Loader – Android/Termux Setup"
step "============================================================"
echo

# ── Step 1: Update package index ────────────────────────────────
step "[1/4] Updating Termux packages..."
pkg update -y
pkg upgrade -y
echo

# ── Step 2: Install system dependencies ─────────────────────────
step "[2/4] Installing dependencies..."
pkg install -y python python-pip parted dosfstools util-linux

# Optional: tsu for root access (needed for drive partitioning)
if ! command -v tsu >/dev/null 2>&1; then
    warn "tsu (Termux root helper) not found."
    warn "Drive partitioning requires root. Install with: pkg install tsu"
fi
echo

# ── Step 3: Install Nightmare Loader ────────────────────────────
step "[3/4] Installing Nightmare Loader..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    info "Installing from local checkout: $SCRIPT_DIR"
    pip install -e "$SCRIPT_DIR"
else
    info "Installing from PyPI..."
    pip install nightmare-loader
fi
echo

# ── Step 4: Create Termux:Widget shortcut ───────────────────────
step "[4/4] Creating Termux:Widget shortcut..."
nightmare-loader install-launcher
echo

# ── Done ────────────────────────────────────────────────────────
echo
echo -e "${GREEN}============================================================${RESET}"
echo -e "${GREEN} Setup complete!${RESET}"
echo
echo " Basic usage:"
echo "   nightmare-loader ui               (start web UI – open URL in browser)"
echo "   nightmare-loader --help           (CLI help)"
echo "   nightmare-loader install-launcher (re-create widget shortcut)"
echo "   nightmare-loader kit              (show the full 64 GB kit plan)"
echo "   nightmare-loader download --list  (list all downloadable distros)"
echo
echo " For drive partitioning (requires root + OTG USB cable on Android):"
echo "   pkg install tsu"
echo "   tsu -c 'nightmare-loader prepare /dev/sda'"
echo
echo " Termux:Widget shortcut:"
echo "   Install 'Termux:Widget' from F-Droid, add the widget to"
echo "   your home screen, and tap 'nightmare-loader' to launch."
echo
echo -e "${BOLD}================================================================${RESET}"
echo -e "${BOLD} 64 GB FULL KIT – Never be stuck without a working computer     ${RESET}"
echo -e "${BOLD}================================================================${RESET}"
echo
echo -e " ${YELLOW}Shows the full kit plan (sizes + running total):${RESET}"
echo "   nightmare-loader kit"
echo
echo -e " ${YELLOW}Downloads ALL auto-available ISOs to ~/storage/downloads:${RESET}"
echo "   nightmare-loader kit --download --out ~/storage/downloads"
echo
echo -e " ${YELLOW}Downloads repair tools only (~2.3 GB):${RESET}"
echo "   nightmare-loader kit --download --category repair --out ~/storage/downloads"
echo
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD} MANUAL DOWNLOAD REQUIRED – Windows (save to ~/storage/downloads)${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo
echo "  win11-repair  ~5800 MB  Windows 11 ISO (has built-in Startup Repair,"
echo "                          System Restore, Command Prompt, regedit)"
echo "    → https://www.microsoft.com/en-us/software-download/windows11"
echo "    After download: nightmare-loader add /dev/sdX Win11_*.iso"
echo
echo "  win10-repair  ~4700 MB  Windows 10 ISO (same repair tools as above)"
echo "    → https://www.microsoft.com/en-us/software-download/windows10"
echo "    After download: nightmare-loader add /dev/sdX Win10_*.iso"
echo
echo "  hirens        ~700 MB   Hiren's BootCD PE – full Windows 11 PE with"
echo "                          NirSoft registry tools, password reset,"
echo "                          antivirus, partition wizard, and 100+ utilities"
echo "    → https://www.hirensbootcd.org/download/"
echo "    After download: nightmare-loader add /dev/sdX Hirens*.iso"
echo
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD} AUTO-DOWNLOAD – Repair & Recovery tools (~2 275 MB)          ${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo
echo "  rescuezilla   ~780 MB   Graphical disk imaging & Windows file recovery"
echo "  systemrescue  ~800 MB   CLI repair: chntpw, ntfsfix, testdisk, photorec"
echo "  gparted       ~600 MB   Partition resize, repair and management"
echo "  clonezilla    ~450 MB   Full-disk backup and bare-metal restore"
echo "  memtest86plus  ~15 MB   RAM hardware diagnostic"
echo "  shredos        ~30 MB   Secure drive wipe"
echo
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD} AUTO-DOWNLOAD – Linux desktops (~8 300 MB)                   ${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo
echo "  ubuntu        ~5800 MB  Ubuntu 24.04 LTS – daily driver"
echo "  mint          ~2800 MB  Linux Mint 22.1 Cinnamon – Windows-like desktop"
echo "  fedora        ~2200 MB  Fedora 41 Workstation – cutting-edge Linux"
echo
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD} AUTO-DOWNLOAD – Lightweight / backup OS (~5 100 MB)          ${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo
echo "  debian        ~3200 MB  Debian Live 12 – rock-solid base OS"
echo "  mxlinux       ~1900 MB  MX Linux – fast, great live-boot tools"
echo
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD} AUTO-DOWNLOAD – Security & privacy (~8 200 MB)               ${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo
echo "  kali          ~4100 MB  Kali Linux – penetration testing"
echo "  tails         ~1300 MB  Tails – anonymous, amnesic OS"
echo "  parrot-home   ~2400 MB  Parrot Home – privacy-focused desktop"
echo
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD} AUTO-DOWNLOAD – Advanced / power-user (~3 700 MB)            ${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo
echo "  arch          ~900 MB   Arch Linux – bleeding edge, minimal"
echo "  endeavouros  ~2800 MB   EndeavourOS – Arch with a friendly installer"
echo
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo -e "${BOLD} TOTALS                                                        ${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────────────────────${RESET}"
echo
echo "  Auto-downloadable   : ~27 575 MB  (~26.9 GB)"
echo "  Manual (Windows)    : ~11 200 MB  (~10.9 GB)"
echo "  Grand total         : ~38 775 MB  (~37.9 GB)"
echo "  Remaining on 64 GB  : ~26 585 MB  (~26.0 GB spare)"
echo
echo -e "${BOLD} All other available distros:${RESET}"
echo "   nightmare-loader download --list"
echo
echo -e "${GREEN}================================================================${RESET}"


