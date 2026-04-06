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
echo "   nightmare-loader ui              (start web UI – open URL in browser)"
echo "   nightmare-loader --help          (CLI help)"
echo "   nightmare-loader install-launcher (re-create widget shortcut)"
echo
echo " For drive partitioning:"
echo "   pkg install tsu                  (root helper)"
echo "   tsu -c 'nightmare-loader prepare /dev/sda'"
echo
echo " Termux:Widget shortcut:"
echo "   Install 'Termux:Widget' from F-Droid, add the widget to"
echo "   your home screen, and tap 'nightmare-loader' to launch."
echo
echo -e "${BOLD}============================================================${RESET}"
echo -e "${BOLD} Supported distros – download with nightmare-loader download${RESET}"
echo -e "${BOLD}============================================================${RESET}"
echo
echo "  List all downloadable distros:"
echo "    nightmare-loader download --list"
echo
echo "  Download a single distro:"
echo "    nightmare-loader download ubuntu --out ~/storage/downloads"
echo
echo "  Download ALL distros at once:"
echo "    nightmare-loader download --all --out ~/storage/downloads"
echo
echo -e "  ${YELLOW}Available distros (key → label, approx. size):${RESET}"
echo
echo "    ubuntu          Ubuntu 24.04 LTS                    ~5800 MB"
echo "    ubuntu-22       Ubuntu 22.04 LTS                    ~4700 MB"
echo "    kubuntu         Kubuntu 24.04 LTS                   ~3900 MB"
echo "    xubuntu         Xubuntu 24.04 LTS                   ~3200 MB"
echo "    lubuntu         Lubuntu 24.04 LTS                   ~2800 MB"
echo "    ubuntu-studio   Ubuntu Studio 24.04 LTS             ~4800 MB"
echo "    debian          Debian Live 12 (GNOME)              ~3200 MB"
echo "    fedora          Fedora 41 Workstation               ~2200 MB"
echo "    arch            Arch Linux (rolling, latest)        ~900 MB"
echo "    manjaro         Manjaro GNOME                       ~4200 MB"
echo "    mint            Linux Mint 22.1 Cinnamon            ~2800 MB"
echo "    mint-mate       Linux Mint 22.1 MATE                ~2800 MB"
echo "    opensuse        openSUSE Leap 15.6 (GNOME)          ~1200 MB"
echo "    opensuse-tw     openSUSE Tumbleweed                 ~1300 MB"
echo "    kali            Kali Linux 2024.4                   ~4100 MB"
echo "    tails           Tails 6.11                          ~1300 MB"
echo "    parrot          Parrot Security 6.3                 ~5100 MB"
echo "    parrot-home     Parrot Home 6.3                     ~2400 MB"
echo "    blackarch       BlackArch Linux (full, ~20 GB)      ~20000 MB"
echo "    whonix          Whonix 17                           ~1900 MB"
echo "    zorin           Zorin OS 17 Core                    ~3500 MB"
echo "    popos           Pop!_OS 22.04                       ~2600 MB"
echo "    elementary      elementary OS 8                     ~2900 MB"
echo "    mxlinux         MX Linux 23.5                       ~1900 MB"
echo "    endeavouros     EndeavourOS (Gemini)                ~2800 MB"
echo "    garuda          Garuda Linux (dr460nized)           ~3100 MB"
echo
echo "  NOTE: ISOs not available for direct download:"
echo "    hirens     – Hiren's BootCD PE  (download manually from https://www.hirensbootcd.org)"
echo "    chromeos   – ChromeOS Flex      (download via USB Installer from https://chromeenterprise.google)"
echo "    windows    – Windows ISO        (download from https://www.microsoft.com/en-us/software-download)"
echo
echo -e "${GREEN}============================================================${RESET}"

