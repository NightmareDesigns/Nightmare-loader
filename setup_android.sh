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
# Root vs. no-root:
#   Nightmare Loader works in two modes on Android:
#
#   WITHOUT ROOT (works on any Android device):
#     - Inspect ISO files:      nightmare-loader info my.iso
#     - Detect USB drives:      nightmare-loader drives
#     - Launch the web UI:      nightmare-loader ui
#     - Manage ISOs on a drive that Android has already mounted
#       (e.g. USB OTG at /storage/XXXX-XXXX) using --mount-point:
#         nightmare-loader list   /dev/sda --mount-point /storage/XXXX-XXXX
#         nightmare-loader add    /dev/sda my.iso --mount-point /storage/XXXX-XXXX
#         nightmare-loader remove /dev/sda my.iso --mount-point /storage/XXXX-XXXX
#         nightmare-loader update /dev/sda --mount-point /storage/XXXX-XXXX
#
#   WITH ROOT (rooted device + tsu):
#     - All of the above, plus:
#     - Partition and format a USB drive:
#         tsu -c 'nightmare-loader prepare /dev/sda'
#     - Mount/unmount drives automatically (no --mount-point needed):
#         tsu -c 'nightmare-loader add /dev/sda my.iso'
#
#   Termux:Widget add-on (from F-Droid) lets you launch the app from the
#   Android home screen.

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
    warn "Without root you can still manage ISOs on already-mounted drives"
    warn "using the --mount-point option."
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
echo " Usage (no root required):"
echo "   nightmare-loader info my.iso         (inspect an ISO)"
echo "   nightmare-loader drives              (list detected USB drives)"
echo "   nightmare-loader ui                  (start web UI – open URL in browser)"
echo "   nightmare-loader install-launcher    (re-create widget shortcut)"
echo
echo " Managing ISOs without root (drive mounted by Android via USB OTG):"
echo "   nightmare-loader list   /dev/sda --mount-point /storage/XXXX-XXXX"
echo "   nightmare-loader add    /dev/sda my.iso --mount-point /storage/XXXX-XXXX"
echo "   nightmare-loader remove /dev/sda my.iso --mount-point /storage/XXXX-XXXX"
echo "   nightmare-loader update /dev/sda --mount-point /storage/XXXX-XXXX"
echo
echo " Root-only operations (requires rooted device + tsu):"
echo "   pkg install tsu"
echo "   tsu -c 'nightmare-loader prepare /dev/sda'"
echo "   tsu -c 'nightmare-loader add /dev/sda my.iso'"
echo
echo " Termux:Widget shortcut:"
echo "   Install 'Termux:Widget' from F-Droid, add the widget to"
echo "   your home screen, and tap 'nightmare-loader' to launch."
echo -e "${GREEN}============================================================${RESET}"
