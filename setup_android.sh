#!/data/data/com.termux/files/usr/bin/bash
# setup_android.sh
# All-in-one Termux setup script for Nightmare Loader on Android.
# Installs every dependency needed to run Nightmare Loader AND to build the
# bootable live ISO – all in a single pass.
#
# Requirements:
#   - Termux (https://github.com/termux/termux-app) installed from F-Droid
#     or GitHub Releases (NOT the Google Play version – it is outdated).
#   - Run this script inside a Termux session.
#
# What this script does:
#   1. Updates Termux packages
#   2. Installs runtime dependencies (Python, parted, dosfstools, util-linux)
#   3. Installs ISO build tools (squashfs-tools, xorriso, mtools, curl,
#      cpio, gzip, qemu-user-x86-64) and tsu (root helper)
#   4. Installs Nightmare Loader from the local checkout (or from PyPI)
#   5. Creates a Termux:Widget launcher shortcut in ~/.shortcuts/
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
#         tsu bash -c 'nightmare-loader prepare /dev/sda'
#     - Mount/unmount drives automatically (no --mount-point needed):
#         tsu bash -c 'nightmare-loader add /dev/sda my.iso'
#     - Build the bootable live ISO:
#         nightmare-loader build-iso --output /sdcard/nightmare-loader-live.iso
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
step " Nightmare Loader – Android/Termux All-in-One Setup"
step "============================================================"
echo

# ── Step 1: Update package index ────────────────────────────────
step "[1/5] Updating Termux packages..."
pkg update -y
pkg upgrade -y
echo

# ── Step 2: Install runtime dependencies ────────────────────────
step "[2/5] Installing runtime dependencies..."
pkg install -y python python-pip parted dosfstools util-linux
echo

# ── Step 3: Install ISO build tools + tsu ───────────────────────
step "[3/5] Installing ISO build tools..."
# squashfs-tools  – mksquashfs to create the live filesystem image
# xorriso         – ISO packager used by grub-mkrescue
# mtools          – FAT/El Torito helpers used by grub-mkrescue
# curl            – download Alpine Linux minirootfs during the build
# cpio / gzip     – create the custom initramfs
# qemu-user-x86-64 – run x86_64 binaries (grub-mkrescue etc.) on ARM64
pkg install -y squashfs-tools xorriso mtools curl cpio gzip qemu-user-x86-64
echo

# tsu: the Termux root helper – needed for drive partitioning and ISO build.
# pkg install tsu may fail on non-rooted devices (the package is a stub that
# just prints an error at runtime), so we allow it to fail silently here.
if pkg install -y tsu 2>/dev/null; then
    info "tsu installed – root operations available."
else
    warn "tsu could not be installed (device may not be rooted)."
    warn "Drive partitioning and ISO building require root."
    warn "On a rooted device, install tsu manually: pkg install tsu"
fi
echo

# ── Step 4: Install Nightmare Loader ────────────────────────────
step "[4/5] Installing Nightmare Loader..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    info "Installing from local checkout: $SCRIPT_DIR"
    pip install -e "$SCRIPT_DIR"
else
    info "Installing from PyPI..."
    pip install nightmare-loader
fi
echo

# ── Step 5: Create Termux:Widget shortcut ───────────────────────
step "[5/5] Creating Termux:Widget shortcut..."
nightmare-loader install-launcher
echo

# ── Done ────────────────────────────────────────────────────────
echo
echo -e "${GREEN}============================================================${RESET}"
echo -e "${GREEN} All-in-one setup complete!${RESET}"
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
echo "   tsu bash -c 'nightmare-loader prepare /dev/sda'   (partition a USB drive)"
echo "   tsu bash -c 'nightmare-loader add /dev/sda my.iso'"
echo
echo " Building the bootable live ISO (requires root via tsu):"
echo "   nightmare-loader build-iso --output /sdcard/nightmare-loader-live.iso"
echo "   (or: tsu bash -c 'bash build_iso.sh --output /sdcard/nightmare-loader-live.iso')"
echo "   Takes ~10–20 minutes. Uses Alpine Linux x86_64 + QEMU emulation."
echo "   Once built:"
echo "     • EtchDroid (no root): copy ISO to phone, plug USB drive via OTG, write."
echo "     • DriveDroid (root):   serve ISO directly from your phone as virtual USB."
echo
echo " Termux:Widget shortcut:"
echo "   Install 'Termux:Widget' from F-Droid, add the widget to"
echo "   your home screen, and tap 'nightmare-loader' to launch."
echo -e "${GREEN}============================================================${RESET}"
