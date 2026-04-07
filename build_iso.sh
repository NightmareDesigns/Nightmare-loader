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

# Install Nightmare Loader
pip3 install --break-system-packages nightmare-loader 2>/dev/null \
  || pip3 install nightmare-loader

# Verify installation
nightmare-loader --version
"

# Copy the local source tree into the chroot so users can also run from source
info "Copying Nightmare Loader source into live image..."
cp -a "$SCRIPT_DIR" "$ROOTFS/opt/nightmare-loader"
chroot "$ROOTFS" /bin/bash -c "
pip3 install --break-system-packages -e /opt/nightmare-loader 2>/dev/null \
  || pip3 install -e /opt/nightmare-loader
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
# Stage 5 – Write the GRUB configuration for the live ISO
# ---------------------------------------------------------------------------

step "Stage 5/6 – Writing GRUB configuration"

mkdir -p "$ISO_STAGE/boot/grub"
cat > "$ISO_STAGE/boot/grub/grub.cfg" <<'GRUBCFG'
# Nightmare Loader – Live ISO boot menu
# This is the GRUB config embedded in the ISO itself (not the USB drive's config).

set default=0
set timeout=10

insmod all_video
insmod gfxterm

if loadfont ($root)/boot/grub/fonts/unicode.pf2; then
    set gfxmode=auto
    terminal_output gfxterm
fi

menuentry "Nightmare Loader Live" {
    linux   /live/vmlinuz boot=live quiet splash ---
    initrd  /live/initrd.img
}

menuentry "Nightmare Loader Live (verbose boot)" {
    linux   /live/vmlinuz boot=live
    initrd  /live/initrd.img
}

menuentry "Nightmare Loader Live (safe mode)" {
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

menuentry "Reboot" { reboot }
menuentry "Power Off" { halt }
GRUBCFG

# Copy the Nightmare Loader GRUB theme into the live ISO as well
THEME_SRC="$SCRIPT_DIR/nightmare_loader/theme/theme.txt"
if [[ -f "$THEME_SRC" ]]; then
    mkdir -p "$ISO_STAGE/boot/grub/themes/nightmare"
    cp "$THEME_SRC" "$ISO_STAGE/boot/grub/themes/nightmare/theme.txt"
    # Enable theme in grub.cfg
    sed -i '/terminal_output gfxterm/a\\    set theme=($root)/boot/grub/themes/nightmare/theme.txt' \
        "$ISO_STAGE/boot/grub/grub.cfg"
    info "GRUB theme installed"
fi

# ---------------------------------------------------------------------------
# Stage 6 – Package everything into a hybrid BIOS+UEFI ISO
# ---------------------------------------------------------------------------

step "Stage 6/6 – Building hybrid ISO with grub-mkrescue"

grub-mkrescue \
    --output="$OUTPUT_ISO" \
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
