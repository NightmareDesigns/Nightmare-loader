#!/usr/bin/env bash
# build_image.sh
# Build a bootable Nightmare Loader disk image (.img) ready to flash with
# Rufus (Windows), dd (Linux/macOS), or balenaEtcher.
#
# The image contains:
#   - MBR partition table + single FAT32 partition (BIOS + UEFI hybrid)
#   - GRUB2 for legacy BIOS (i386-pc)
#   - GRUB2 for UEFI (x86_64-efi, EFI/BOOT/BOOTX64.EFI)
#   - Nightmare Loader GRUB theme
#   - Auto-discovery grub.cfg — GRUB scans /isos/*.iso at boot time; no
#     additional software needed on the host after flashing
#   - Empty /isos directory ready for ISO files
#
# Requirements (Debian/Ubuntu):
#   sudo apt install grub2-common grub-pc-bin grub-efi-amd64-bin parted dosfstools python3 python3-pip
#
# Usage:
#   sudo bash build_image.sh                          # 256 MiB image (default)
#   sudo bash build_image.sh --size 512               # 512 MiB image
#   sudo bash build_image.sh --label MYUSB            # custom volume label
#   sudo bash build_image.sh --output /tmp/boot.img   # custom output path
#
# Output: dist/nightmare-loader.img  (or the path given via --output)
#
# After building, flash the image:
#   Rufus (Windows) : select the .img, choose "DD Image" write mode, click START
#   dd    (Linux)   : sudo dd if=dist/nightmare-loader.img of=/dev/sdX bs=4M status=progress
#
# Then copy your .iso files into the  isos/  folder on the USB drive and boot.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SIZE_MIB=256
LABEL="NIGHTMARE"
OUTPUT="dist/nightmare-loader.img"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --size|-s)   SIZE_MIB="$2"; shift 2 ;;
        --label|-l)  LABEL="$2";    shift 2 ;;
        --output|-o) OUTPUT="$2";   shift 2 ;;
        --help|-h)
            sed -n '2,/^set -/p' "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo "============================================================"
echo " Nightmare Loader -- Bootable Image Builder"
echo "============================================================"
echo ""
echo "  Size   : ${SIZE_MIB} MiB"
echo "  Label  : ${LABEL}"
echo "  Output : ${OUTPUT}"
echo ""

# ---------------------------------------------------------------------------
# Root check
# ---------------------------------------------------------------------------
if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo bash build_image.sh)."
    exit 1
fi

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
echo "[0/4] Checking dependencies..."
MISSING=()
for tool in dd parted losetup mkfs.fat grub-install mount umount python3; do
    command -v "$tool" >/dev/null 2>&1 || MISSING+=("$tool")
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo ""
    echo "ERROR: The following tools are missing: ${MISSING[*]}"
    echo ""
    echo "Install them on Debian/Ubuntu with:"
    echo "  sudo apt install grub2-common grub-pc-bin grub-efi-amd64-bin parted dosfstools python3 python3-pip"
    exit 1
fi
echo "  All required tools found."
echo ""

# ---------------------------------------------------------------------------
# Install nightmare-loader Python package (for grub.cfg generation)
# ---------------------------------------------------------------------------
echo "[1/4] Installing nightmare-loader package..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
pip3 install --quiet -e "$SCRIPT_DIR"
echo "  Done."
echo ""

# ---------------------------------------------------------------------------
# Build the image via the CLI
# ---------------------------------------------------------------------------
echo "[2/4] Building bootable image..."
nightmare-loader build-image \
    --output "$OUTPUT" \
    --size   "$SIZE_MIB" \
    --label  "$LABEL"
echo ""

# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------
echo "[3/4] Generating SHA-256 checksum..."
sha256sum "$OUTPUT" | tee "${OUTPUT%.img}.sha256"
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "[4/4] Build complete!"
echo ""
echo "  Image    : $OUTPUT"
echo "  Checksum : ${OUTPUT%.img}.sha256"
echo ""
echo "Flash to USB:"
echo "  Rufus (Windows) : select $OUTPUT, choose 'DD Image' write mode, click START"
echo "  dd    (Linux)   : sudo dd if=$OUTPUT of=/dev/sdX bs=4M status=progress"
echo ""
echo "After flashing:"
echo "  1. Copy your .iso files into the  isos/  folder on the USB drive."
echo "  2. Boot from the USB drive — GRUB finds your ISOs automatically."
echo ""
