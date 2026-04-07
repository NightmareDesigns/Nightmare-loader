#!/usr/bin/env bash
# build_iso.sh
# Build a bootable Nightmare Loader live ISO (hybrid BIOS + UEFI).
#
# The resulting ISO boots on any x86-64 PC regardless of firmware.  On first
# boot it drops into a root shell running the Nightmare Loader welcome screen
# from which you can prepare USB drives, add ISOs, and use the web UI.
#
# Requirements (Debian/Ubuntu host or Dockerfile.iso-builder):
#   debootstrap mksquashfs grub-pc-bin grub-efi-amd64-bin xorriso mtools
#
# Usage:
#   sudo ./build_iso.sh [--output PATH] [--suite bookworm]
#
# Output:
#   nightmare-loader-live.iso  (in the current directory, or --output path)
#
# To build inside Docker (no root required on the host):
#   docker build -t nightmare-iso-builder -f Dockerfile.iso-builder .
#   docker run --rm --privileged -v "$(pwd)":/out nightmare-iso-builder

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
step()  { echo -e "\n${BOLD}── $* ──${RESET}"; }
die()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Defaults / argument parsing
# ---------------------------------------------------------------------------

SUITE="bookworm"
OUTPUT_ISO="$(pwd)/nightmare-loader-live.iso"
MIRROR="https://deb.debian.org/debian"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)  OUTPUT_ISO="$2"; shift 2 ;;
        --suite)   SUITE="$2";     shift 2 ;;
        --mirror)  MIRROR="$2";    shift 2 ;;
        -h|--help)
            echo "Usage: sudo $0 [--output PATH] [--suite bookworm] [--mirror URL]"
            exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

# Make the output path absolute before we cd around
OUTPUT_ISO="$(realpath -m "$OUTPUT_ISO")"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING="$(mktemp -d /tmp/nightmare-iso-XXXXXX)"
ROOTFS="$STAGING/rootfs"
ISO_STAGE="$STAGING/iso"

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

step "Checking prerequisites"

[[ $EUID -eq 0 ]] || die "This script must be run as root (or inside Docker with --privileged)."

for cmd in debootstrap mksquashfs grub-mkrescue xorriso mtools; do
    if command -v "$cmd" &>/dev/null; then
        info "  $cmd  ✓"
    else
        die "'$cmd' is not installed. Install it with:\n  apt-get install debootstrap squashfs-tools grub-pc-bin grub-efi-amd64-bin xorriso mtools"
    fi
done

# ---------------------------------------------------------------------------
# Stage 1 – Bootstrap a minimal Debian root filesystem
# ---------------------------------------------------------------------------

step "Stage 1/6 – Bootstrapping Debian $SUITE"

mkdir -p "$ROOTFS"
debootstrap \
    --variant=minbase \
    --include=linux-image-amd64,live-boot,live-boot-initramfs-tools,systemd-sysv \
    "$SUITE" "$ROOTFS" "$MIRROR"

# ---------------------------------------------------------------------------
# Stage 2 – Install Nightmare Loader and its runtime dependencies
# ---------------------------------------------------------------------------

step "Stage 2/6 – Installing packages and Nightmare Loader"

# Write an APT sources list that avoids interactive prompts
cat > "$ROOTFS/etc/apt/sources.list" <<EOF
deb $MIRROR $SUITE main contrib non-free
EOF

# Prevent services from starting inside the chroot
cat > "$ROOTFS/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
exit 101
EOF
chmod +x "$ROOTFS/usr/sbin/policy-rc.d"

# Bind-mount kernel pseudo-filesystems so chroot commands work correctly
for fs in dev dev/pts proc sys run; do
    mkdir -p "$ROOTFS/$fs"
    mount --bind "/$fs" "$ROOTFS/$fs"
done

cleanup_mounts() {
    for fs in run sys proc dev/pts dev; do
        umount -lf "$ROOTFS/$fs" 2>/dev/null || true
    done
}
trap cleanup_mounts EXIT

chroot "$ROOTFS" /bin/bash -c "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip \
    parted dosfstools genisoimage \
    grub-pc-bin grub-efi-amd64-bin grub-common \
    ca-certificates curl \
    bash-completion less

# pip3 on Debian bookworm requires --break-system-packages when installing
# outside a virtualenv; older pip versions don't recognise the flag, so fall
# back without it.
pip3_install() { pip3 install --break-system-packages \"\$@\" 2>/dev/null || pip3 install \"\$@\"; }

# Install Nightmare Loader
pip3_install nightmare-loader

# Verify installation
nightmare-loader --version
"

# Copy the local source tree into the chroot so users can also run from source
info "Copying Nightmare Loader source into live image..."
cp -a "$SCRIPT_DIR" "$ROOTFS/opt/nightmare-loader"
chroot "$ROOTFS" /bin/bash -c "
pip3_install() { pip3 install --break-system-packages \"\$@\" 2>/dev/null || pip3 install \"\$@\"; }
pip3_install -e /opt/nightmare-loader
"

# ---------------------------------------------------------------------------
# Stage 3 – Apply iso_root overlay (auto-login, welcome script, profile)
# ---------------------------------------------------------------------------

step "Stage 3/6 – Applying iso_root overlay"

ISO_ROOT_SRC="$SCRIPT_DIR/iso_root"
if [[ -d "$ISO_ROOT_SRC" ]]; then
    cp -a "$ISO_ROOT_SRC/." "$ROOTFS/"
    info "Overlay applied from $ISO_ROOT_SRC"
else
    warn "iso_root/ directory not found – skipping overlay"
fi

# Set root password to empty (the live image is ephemeral)
chroot "$ROOTFS" /bin/bash -c "passwd -d root"

# Hostname for the live system
echo "nightmare-loader-live" > "$ROOTFS/etc/hostname"

# Disable the policy-rc.d blocker now that we're done installing packages
rm -f "$ROOTFS/usr/sbin/policy-rc.d"

# Remove APT caches to trim image size
chroot "$ROOTFS" /bin/bash -c "
apt-get clean
rm -rf /var/lib/apt/lists/*
"

cleanup_mounts
trap - EXIT

# ---------------------------------------------------------------------------
# Stage 4 – Create the SquashFS live filesystem
# ---------------------------------------------------------------------------

step "Stage 4/6 – Creating SquashFS (this may take a few minutes)"

mkdir -p "$ISO_STAGE/live"
mksquashfs "$ROOTFS" "$ISO_STAGE/live/filesystem.squashfs" \
    -comp xz -noappend -e "$ROOTFS/proc/*" -e "$ROOTFS/sys/*" \
    -e "$ROOTFS/dev/*" -e "$ROOTFS/run/*" -e "$ROOTFS/tmp/*"

# Copy kernel and initrd from the bootstrapped root
VMLINUZ="$(ls "$ROOTFS/boot/vmlinuz-"* | sort | tail -1)"
INITRD="$(ls  "$ROOTFS/boot/initrd.img-"* | sort | tail -1)"

[[ -f "$VMLINUZ" ]] || die "vmlinuz not found in $ROOTFS/boot/"
[[ -f "$INITRD"  ]] || die "initrd not found in $ROOTFS/boot/"

cp "$VMLINUZ" "$ISO_STAGE/live/vmlinuz"
cp "$INITRD"  "$ISO_STAGE/live/initrd.img"

info "Kernel : $VMLINUZ"
info "Initrd : $INITRD"
info "Squash : $(du -sh "$ISO_STAGE/live/filesystem.squashfs" | cut -f1)"

# ---------------------------------------------------------------------------
# Stage 5 – Install the Nightmare Loader GRUB theme (the preloader) and
#            write the live ISO's GRUB configuration.
#
# The themed pre-loader is a core part of the Nightmare Loader identity: it
# shows the dark matrix-inspired "NIGHTMARE LOADER" splash (red title, green
# menu, black background) before the boot menu is drawn.  It is installed on
# every USB drive that `nightmare-loader prepare` touches via
# install_grub_theme() in grub.py.  The live ISO receives exactly the same
# treatment so the experience is identical whether you boot from a prepared
# USB drive or from the live image itself.
# ---------------------------------------------------------------------------

step "Stage 5/6 – Installing preloader theme and writing GRUB configuration"

# The theme is mandatory – abort loudly if it is missing so the build never
# silently ships an ISO without the Nightmare Loader branded pre-loader.
THEME_SRC="$SCRIPT_DIR/nightmare_loader/theme/theme.txt"
[[ -f "$THEME_SRC" ]] \
    || die "Nightmare Loader GRUB theme not found at $THEME_SRC – cannot build ISO without the preloader."

THEME_DEST="$ISO_STAGE/boot/grub/themes/nightmare"
mkdir -p "$THEME_DEST"
cp "$THEME_SRC" "$THEME_DEST/theme.txt"
info "Preloader theme installed → $THEME_DEST/theme.txt"

# Build the grub.cfg with the theme activated from the first line that can
# activate it.  This mirrors the _make_header() function in grub.py exactly,
# adjusted for ISO paths (no `search` by label is needed since grub-mkrescue
# sets $root correctly for the CD/USB it was loaded from).
mkdir -p "$ISO_STAGE/boot/grub"
cat > "$ISO_STAGE/boot/grub/grub.cfg" <<'GRUBCFG'
# Nightmare Loader – Live ISO boot menu
# Auto-generated by build_iso.sh – do not edit by hand.

set default=0
set timeout=10

insmod part_gpt
insmod part_msdos
insmod fat
insmod iso9660
insmod all_video
insmod gfxterm

# Enable the graphical terminal and load the Nightmare Loader preloader theme
# so the branded splash is shown before the menu appears.  Falls back silently
# to text mode on systems that do not support graphical output (mirrors the
# behaviour of the GRUB config installed on prepared USB drives).
if loadfont ($root)/boot/grub/fonts/unicode.pf2; then
    set gfxmode=auto
    terminal_output gfxterm
    set theme=($root)/boot/grub/themes/nightmare/theme.txt
fi

menuentry "Nightmare Loader Live" {
    linux   /live/vmlinuz boot=live quiet splash ---
    initrd  /live/initrd.img
}

menuentry "Nightmare Loader Live (verbose boot)" {
    linux   /live/vmlinuz boot=live
    initrd  /live/initrd.img
}

menuentry "Nightmare Loader Live (safe mode – nomodeset)" {
    linux   /live/vmlinuz boot=live nomodeset
    initrd  /live/initrd.img
}

menuentry "Boot from first hard disk" {
    insmod chain
    insmod part_msdos
    insmod part_gpt
    set root=(hd0)
    chainloader +1
}

menuentry "Reboot"    { reboot }
menuentry "Power Off" { halt   }
GRUBCFG

info "GRUB configuration written with preloader theme active"

# ---------------------------------------------------------------------------
# Stage 6 – Package everything into a hybrid BIOS+UEFI ISO
# ---------------------------------------------------------------------------

step "Stage 6/6 – Building hybrid ISO with grub-mkrescue"

# --fonts=unicode embeds the unicode.pf2 bitmap font into the image so
# `loadfont ($root)/boot/grub/fonts/unicode.pf2` in grub.cfg succeeds and the
# graphical preloader theme is actually displayed at boot.
grub-mkrescue \
    --output="$OUTPUT_ISO" \
    --fonts=unicode \
    "$ISO_STAGE" \
    -- \
    -volid "NIGHTMARE-LIVE" \
    -iso-level 3 \
    -rock \
    -joliet

SIZE="$(du -sh "$OUTPUT_ISO" | cut -f1)"

echo
echo -e "${GREEN}============================================================${RESET}"
echo -e "${GREEN} Build complete!${RESET}"
echo
echo "  ISO  : $OUTPUT_ISO"
echo "  Size : $SIZE"
echo
echo " To write to a USB drive:"
echo "   sudo dd if=$OUTPUT_ISO of=/dev/sdX bs=4M status=progress conv=fsync"
echo
echo " To use from your phone:"
echo "   • EtchDroid (no root): copy the ISO to your phone, plug in a USB"
echo "     drive via OTG, write the ISO to the drive, then boot any PC from it."
echo "   • DriveDroid (root required): serve the ISO directly from your phone"
echo "     as a virtual USB drive – no physical USB stick needed."
echo -e "${GREEN}============================================================${RESET}"

# Clean up staging area
rm -rf "$STAGING"
