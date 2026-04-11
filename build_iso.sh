#!/usr/bin/env bash
# build_iso.sh
# Build a bootable Nightmare Loader live ISO (hybrid BIOS + UEFI).
#
# The resulting ISO boots on any x86-64 PC regardless of firmware.  On first
# boot it drops into a root shell running the Nightmare Loader welcome screen
# from which you can prepare USB drives, add ISOs, and use the web UI.
#
# TWO BUILD PATHS
# ─────────────────────────────────────────────────────────────────
#  Linux host  (default)
#    Uses debootstrap + Debian bookworm as the live rootfs.  Full live-boot
#    support via the debian live-boot package.
#    Required: debootstrap mksquashfs grub-pc-bin grub-efi-amd64-bin xorriso mtools
#
#  Termux / Android  (auto-detected, or use --termux)
#    Uses an Alpine Linux x86_64 minirootfs + QEMU user-mode emulation for
#    transparent x86_64 chroot on ARM64.  grub-mkrescue runs inside the
#    Alpine chroot (via QEMU) so genuine x86_64 GRUB modules are used.
#    Required Termux packages:
#      pkg install squashfs-tools xorriso mtools curl cpio gzip qemu-user-x86-64
#    Root access (tsu) is required in both cases.
#
# Usage:
#   sudo ./build_iso.sh [--output PATH] [--termux] [--no-termux]
#   sudo ./build_iso.sh [--suite bookworm] [--mirror URL]   # Linux only
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

# Auto-detect Termux
if [[ -n "${TERMUX_VERSION:-}" ]] || [[ -d /data/data/com.termux ]]; then
    TERMUX_BUILD=1
else
    TERMUX_BUILD=0
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)       OUTPUT_ISO="$2";  shift 2 ;;
        --suite)        SUITE="$2";       shift 2 ;;
        --mirror)       MIRROR="$2";      shift 2 ;;
        --termux)       TERMUX_BUILD=1;   shift   ;;
        --no-termux)    TERMUX_BUILD=0;   shift   ;;
        -h|--help)
            echo "Usage: sudo $0 [--output PATH] [--termux|--no-termux]"
            echo "       [--suite bookworm] [--mirror URL]"
            exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

OUTPUT_ISO="$(realpath -m "$OUTPUT_ISO")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING="$(mktemp -d /tmp/nightmare-iso-XXXXXX)"
ROOTFS="$STAGING/rootfs"
ISO_STAGE="$STAGING/iso"

# Alpine settings (Termux path only)
ALPINE_VERSION="3.21.3"
ALPINE_ARCH="x86_64"
ALPINE_MIRROR="https://dl-cdn.alpinelinux.org/alpine"

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

step "Checking prerequisites"

[[ $EUID -eq 0 ]] || die "This script must be run as root (tsu on Termux, sudo on Linux)."

if [[ $TERMUX_BUILD -eq 1 ]]; then
    info "Build mode: Termux / Android (Alpine x86_64 + QEMU)"
    MISSING_PKGS=""
    for cmd in mksquashfs xorriso mtools curl cpio gzip; do
        if command -v "$cmd" &>/dev/null; then
            info "  $cmd  ✓"
        else
            warn "  $cmd  ✗  (missing)"
            MISSING_PKGS="$MISSING_PKGS $cmd"
        fi
    done
    # QEMU for x86_64 emulation
    if command -v qemu-x86_64 &>/dev/null; then
        info "  qemu-x86_64  ✓"
        QEMU_BIN="$(command -v qemu-x86_64)"
    else
        warn "  qemu-x86_64  ✗  (missing)"
        MISSING_PKGS="$MISSING_PKGS qemu-user-x86-64"
    fi
    if [[ -n "${MISSING_PKGS# }" ]]; then
        echo
        echo "  Install missing Termux packages with:"
        echo "    pkg install squashfs-tools xorriso mtools curl cpio gzip qemu-user-x86-64"
        die "Missing required packages:${MISSING_PKGS}"
    fi
else
    info "Build mode: native Linux (Debian bookworm + debootstrap)"
    for cmd in debootstrap mksquashfs grub-mkrescue xorriso mtools; do
        if command -v "$cmd" &>/dev/null; then
            info "  $cmd  ✓"
        else
            die "'$cmd' not found. Install:\n  apt-get install debootstrap squashfs-tools grub-pc-bin grub-efi-amd64-bin xorriso mtools"
        fi
    done
fi

# ---------------------------------------------------------------------------
# Shared: mount / unmount helpers
# ---------------------------------------------------------------------------

MOUNTS_ACTIVE=0

setup_mounts() {
    for fs in dev dev/pts proc sys run; do
        mkdir -p "$ROOTFS/$fs"
        mount --bind "/$fs" "$ROOTFS/$fs"
    done
    MOUNTS_ACTIVE=1
}

cleanup_mounts() {
    if [[ $MOUNTS_ACTIVE -eq 1 ]]; then
        for fs in run sys proc dev/pts dev; do
            umount -lf "$ROOTFS/$fs" 2>/dev/null || true
        done
        MOUNTS_ACTIVE=0
    fi
}

cleanup_all() {
    cleanup_mounts
    # Tear down QEMU binfmt if we set it up
    if [[ -f /proc/sys/fs/binfmt_misc/qemu-x86_64 ]]; then
        echo -1 > /proc/sys/fs/binfmt_misc/qemu-x86_64 2>/dev/null || true
    fi
    rm -rf "$STAGING"
}
trap cleanup_all EXIT

# ---------------------------------------------------------------------------
# Stage 1 – Bootstrap root filesystem
# ---------------------------------------------------------------------------

if [[ $TERMUX_BUILD -eq 1 ]]; then

    step "Stage 1/6 – Downloading Alpine Linux $ALPINE_VERSION x86_64 minirootfs"

    ALPINE_TAR="alpine-minirootfs-${ALPINE_VERSION}-${ALPINE_ARCH}.tar.gz"
    ALPINE_URL="${ALPINE_MIRROR}/v${ALPINE_VERSION%.*}/releases/${ALPINE_ARCH}/${ALPINE_TAR}"

    mkdir -p "$ROOTFS"
    info "Fetching $ALPINE_URL …"
    curl -fL --progress-bar "$ALPINE_URL" | tar -xzf - -C "$ROOTFS"

    # ── Set up QEMU binfmt_misc so x86_64 ELF binaries run transparently ──
    # The 'F' (fix binary) flag makes the kernel open the QEMU interpreter
    # before entering the chroot so Termux's dynamically-linked qemu-x86_64
    # is used even though its ARM64 libs are not inside the x86_64 chroot.
    info "Registering x86_64 binfmt_misc entry with QEMU (F flag)…"
    mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc 2>/dev/null || true

    # Only register if not already registered
    if [[ ! -f /proc/sys/fs/binfmt_misc/qemu-x86_64 ]]; then
        # Magic bytes explained:
        #   \x7fELF          – ELF magic number
        #   \x02             – EI_CLASS=2 (64-bit)
        #   \x01             – EI_DATA=1 (little-endian)
        #   \x01             – EI_VERSION=1
        #   \x00×8           – EI_OSABI + padding
        #   \x02\x00         – e_type=2 (ET_EXEC, executable)
        #   \x3e\x00         – e_machine=0x3e (x86-64 / EM_X86_64)
        # Mask bytes: \xfe on EI_DATA/EI_VERSION allow any ABI byte; \xfe on
        # e_type allows both ET_EXEC and ET_DYN (shared-library executables).
        # The 'C' flag treats the interpreter as a credential-preserving
        # binary; 'F' (fix binary) tells the kernel to open the interpreter
        # file descriptor before entering the chroot so the ARM64 QEMU binary
        # is invoked even though its libs are not present in the x86_64 chroot.
        echo ":qemu-x86_64:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00:\xff\xff\xff\xff\xff\xfe\xfe\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:${QEMU_BIN}:CF" \
            > /proc/sys/fs/binfmt_misc/register \
            || warn "binfmt_misc registration failed – chroot may not work; check kernel config."
    fi
    info "binfmt_misc: $(cat /proc/sys/fs/binfmt_misc/qemu-x86_64 2>/dev/null | head -1 || echo 'unknown')"

else

    step "Stage 1/6 – Bootstrapping Debian $SUITE"

    mkdir -p "$ROOTFS"
    debootstrap \
        --variant=minbase \
        --include=linux-image-amd64,live-boot,live-boot-initramfs-tools,systemd-sysv \
        "$SUITE" "$ROOTFS" "$MIRROR"

fi

# ---------------------------------------------------------------------------
# Stage 2 – Install packages and Nightmare Loader
# ---------------------------------------------------------------------------

# Prevent services from starting inside the chroot
cat > "$ROOTFS/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
exit 101
EOF
chmod +x "$ROOTFS/usr/sbin/policy-rc.d"

setup_mounts

pip3_install() {
    # PEP 668 fix: Debian bookworm marks system Python as externally managed,
    # so plain `pip3 install` fails with error: externally-managed-environment.
    # Use a virtual environment to install packages without touching system Python.
    local venv=/opt/nightmare-venv
    [ -d "$venv" ] || python3 -m venv "$venv" || { echo "Error: Failed to create venv at $venv" >&2; return 1; }
    "$venv/bin/pip" install "$@"
}

if [[ $TERMUX_BUILD -eq 1 ]]; then

    step "Stage 2/6 – Installing Alpine packages and Nightmare Loader (via QEMU)"

    # Write a resolv.conf so apk can reach the network
    cp /etc/resolv.conf "$ROOTFS/etc/resolv.conf" 2>/dev/null || true

    chroot "$ROOTFS" /bin/sh -c "
set -e
# Configure Alpine APK repositories
cat > /etc/apk/repositories << 'REPOS'
https://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION%.*}/main
https://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION%.*}/community
REPOS

apk update
apk add --no-cache \
    linux-lts mkinitfs \
    python3 py3-pip \
    parted dosfstools genisoimage \
    grub grub-bios grub-efi grub-efi-x86_64 \
    xorriso mtools cpio gzip \
    bash ca-certificates curl

# Set bash as root's login shell (welcome script needs it)
sed -i 's|^root:x:0:0:root:/root:/bin/sh\$|root:x:0:0:root:/root:/bin/bash|' /etc/passwd

# Install Nightmare Loader from PyPI
pip3 install --break-system-packages nightmare-loader 2>/dev/null \
    || pip3 install nightmare-loader

# Verify
nightmare-loader --version
"

    # Install Nightmare Loader from local source tree as well
    info "Copying Nightmare Loader source into live image…"
    cp -a "$SCRIPT_DIR" "$ROOTFS/opt/nightmare-loader"
    chroot "$ROOTFS" /bin/sh -c "
pip3 install --break-system-packages -e /opt/nightmare-loader 2>/dev/null \
    || pip3 install -e /opt/nightmare-loader
"

else

    step "Stage 2/6 – Installing Debian packages and Nightmare Loader"

    cat > "$ROOTFS/etc/apt/sources.list" <<EOF
deb $MIRROR $SUITE main contrib non-free
EOF

    chroot "$ROOTFS" /bin/bash -c "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-venv \
    parted dosfstools genisoimage \
    grub-pc-bin grub-efi-amd64-bin grub-common \
    ca-certificates curl bash-completion less

$(declare -f pip3_install)
# Optional: install published PyPI release if available; the editable local
# install below will always overlay (or substitute) it.
# Allow failure if package not yet published on PyPI.
pip3_install nightmare-loader || true
"

    info "Copying Nightmare Loader source into live image…"
    cp -a "$SCRIPT_DIR" "$ROOTFS/opt/nightmare-loader"
    chroot "$ROOTFS" /bin/bash -c "
$(declare -f pip3_install)
pip3_install -e /opt/nightmare-loader
/opt/nightmare-venv/bin/nightmare-loader --version
"

fi

# ---------------------------------------------------------------------------
# Stage 3 – Apply iso_root overlay + platform-specific boot configuration
# ---------------------------------------------------------------------------

step "Stage 3/6 – Applying overlay and configuring live boot"

ISO_ROOT_SRC="$SCRIPT_DIR/iso_root"
if [[ -d "$ISO_ROOT_SRC" ]]; then
    cp -a "$ISO_ROOT_SRC/." "$ROOTFS/"
    info "Overlay applied from $ISO_ROOT_SRC"
else
    warn "iso_root/ not found – skipping overlay"
fi

# Ensure root has no password (ephemeral live image)
chroot "$ROOTFS" /bin/sh -c "passwd -d root" 2>/dev/null || true

echo "nightmare-loader-live" > "$ROOTFS/etc/hostname"

if [[ $TERMUX_BUILD -eq 1 ]]; then
    # Alpine uses BusyBox inittab; configure autologin for root on tty1.
    # /bin/login -f root skips the password check for root.
    if [[ -f "$ROOTFS/etc/inittab" ]]; then
        # Match the exact tty1 getty line format Alpine ships in its minirootfs
        # to avoid accidentally clobbering unrelated inittab entries.
        sed -i 's|tty1::respawn:/sbin/getty.*|tty1::respawn:/bin/login -f root|' "$ROOTFS/etc/inittab"
    else
        echo "tty1::respawn:/bin/login -f root" >> "$ROOTFS/etc/inittab"
    fi
    info "Alpine autologin configured in /etc/inittab"

    # ── Configure mkinitfs for live squashfs boot ──────────────────────────
    # Create a custom feature that adds the drivers needed by
    # nightmare-live-init.sh to find and mount the live medium.
    mkdir -p "$ROOTFS/etc/mkinitfs/features.d"
    cat > "$ROOTFS/etc/mkinitfs/features.d/nightmare-live.modules" << 'FEAT'
kernel/drivers/block/loop.ko*
kernel/fs/squashfs/squashfs.ko*
kernel/fs/isofs/isofs.ko*
kernel/fs/overlayfs/overlay.ko*
FEAT

    cat > "$ROOTFS/etc/mkinitfs/mkinitfs.conf" << 'MCONF'
features="base squashfs nightmare-live"
MCONF
    info "mkinitfs configured with nightmare-live feature"
else
    info "Debian/systemd autologin already provided by iso_root overlay"
fi

rm -f "$ROOTFS/usr/sbin/policy-rc.d"

# Trim APT / APK caches
if [[ $TERMUX_BUILD -eq 1 ]]; then
    chroot "$ROOTFS" /bin/sh  -c "rm -rf /var/cache/apk/*"
else
    chroot "$ROOTFS" /bin/bash -c "apt-get clean && rm -rf /var/lib/apt/lists/*"
fi

cleanup_mounts

# ---------------------------------------------------------------------------
# Stage 4 – SquashFS + kernel/initrd
# ---------------------------------------------------------------------------

step "Stage 4/6 – Creating SquashFS and extracting kernel/initrd"

mkdir -p "$ISO_STAGE/live"

mksquashfs "$ROOTFS" "$ISO_STAGE/live/filesystem.squashfs" \
    -comp xz -noappend \
    -e boot \
    -e proc -e sys -e dev -e run -e tmp

info "Squash: $(du -sh "$ISO_STAGE/live/filesystem.squashfs" | cut -f1)"

if [[ $TERMUX_BUILD -eq 1 ]]; then
    # ── Alpine kernel ──────────────────────────────────────────────────────
    VMLINUZ="$(ls "$ROOTFS/boot/vmlinuz-lts" 2>/dev/null || ls "$ROOTFS/boot/vmlinuz-"* 2>/dev/null | sort | tail -1)"
    [[ -f "$VMLINUZ" ]] || die "vmlinuz not found in $ROOTFS/boot/"
    cp "$VMLINUZ" "$ISO_STAGE/live/vmlinuz"
    info "Kernel: $VMLINUZ"

    # ── Custom initramfs via mkinitfs -i ───────────────────────────────────
    # Copy the live-boot init script into the chroot where mkinitfs can see it.
    INIT_SRC="$SCRIPT_DIR/iso_root/usr/local/bin/nightmare-live-init.sh"
    [[ -f "$INIT_SRC" ]] \
        || die "nightmare-live-init.sh not found at $INIT_SRC"
    cp "$INIT_SRC" "$ROOTFS/tmp/nightmare-live-init.sh"
    chmod +x "$ROOTFS/tmp/nightmare-live-init.sh"

    # Re-mount for the mkinitfs chroot run
    setup_mounts

    KVER="$(ls "$ROOTFS/lib/modules/" | sort | tail -1)"
    [[ -n "$KVER" ]] || die "No kernel modules found in $ROOTFS/lib/modules/"
    info "Building initramfs for kernel $KVER …"

    chroot "$ROOTFS" /bin/sh -c "
mkinitfs -i /tmp/nightmare-live-init.sh \
         -o /boot/initramfs-nightmare \
         '$KVER'
"
    cp "$ROOTFS/boot/initramfs-nightmare" "$ISO_STAGE/live/initrd.img"
    info "Initrd: $(du -sh "$ISO_STAGE/live/initrd.img" | cut -f1)"

    cleanup_mounts

else
    # ── Debian kernel + live-boot initrd ──────────────────────────────────
    VMLINUZ="$(ls "$ROOTFS/boot/vmlinuz-"* 2>/dev/null | sort | tail -1)"
    INITRD="$(ls  "$ROOTFS/boot/initrd.img-"* 2>/dev/null | sort | tail -1)"
    [[ -f "$VMLINUZ" ]] || die "vmlinuz not found in $ROOTFS/boot/"
    [[ -f "$INITRD"  ]] || die "initrd not found in $ROOTFS/boot/"
    cp "$VMLINUZ" "$ISO_STAGE/live/vmlinuz"
    cp "$INITRD"  "$ISO_STAGE/live/initrd.img"
    info "Kernel: $VMLINUZ"
    info "Initrd: $INITRD"
fi

# ---------------------------------------------------------------------------
# Stage 5 – Install the Nightmare Loader GRUB preloader theme and write
#            the live ISO's GRUB configuration.
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

# The theme is mandatory – abort loudly if missing so the build never ships
# an ISO without the Nightmare Loader branded pre-loader.
THEME_SRC="$SCRIPT_DIR/nightmare_loader/theme/theme.txt"
[[ -f "$THEME_SRC" ]] \
    || die "Nightmare Loader GRUB theme not found at $THEME_SRC – cannot build without the preloader."

THEME_DEST="$ISO_STAGE/boot/grub/themes/nightmare"
mkdir -p "$THEME_DEST"
cp "$THEME_SRC" "$THEME_DEST/theme.txt"
info "Preloader theme installed → $THEME_DEST/theme.txt"

# Boot parameters differ by path:
#   Debian:  live-boot reads 'boot=live'; '---' separates kernel params from
#            init params (standard Debian live convention).
#   Alpine:  our custom init needs no special params; 'modules=' list ensures
#            the squashfs and loop drivers are loaded early.
if [[ $TERMUX_BUILD -eq 1 ]]; then
    BOOT_PARAMS="quiet modules=loop,squashfs,sd-mod,usb-storage"
    BOOT_PARAMS_VERBOSE="modules=loop,squashfs,sd-mod,usb-storage"
    BOOT_PARAMS_SAFE="nomodeset modules=loop,squashfs,sd-mod,usb-storage"
else
    BOOT_PARAMS="boot=live quiet splash ---"
    BOOT_PARAMS_VERBOSE="boot=live"
    BOOT_PARAMS_SAFE="boot=live nomodeset"
fi

mkdir -p "$ISO_STAGE/boot/grub"
cat > "$ISO_STAGE/boot/grub/grub.cfg" <<GRUBCFG
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
if loadfont (\$root)/boot/grub/fonts/unicode.pf2; then
    set gfxmode=auto
    terminal_output gfxterm
    set theme=(\$root)/boot/grub/themes/nightmare/theme.txt
fi

menuentry "Nightmare Loader Live" {
    linux   /live/vmlinuz $BOOT_PARAMS
    initrd  /live/initrd.img
}

menuentry "Nightmare Loader Live (verbose boot)" {
    linux   /live/vmlinuz $BOOT_PARAMS_VERBOSE
    initrd  /live/initrd.img
}

menuentry "Nightmare Loader Live (safe mode - nomodeset)" {
    linux   /live/vmlinuz $BOOT_PARAMS_SAFE
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
#
# Termux:  grub-mkrescue runs INSIDE the Alpine x86_64 chroot via QEMU so
#          the genuine x86_64 GRUB module tree is used.  The ISO staging
#          directory is bind-mounted into the chroot.
# Linux:   grub-mkrescue runs natively on the host.
#
# --fonts=unicode embeds the unicode.pf2 bitmap font so the loadfont call
# in grub.cfg succeeds and the graphical preloader theme is displayed.
# ---------------------------------------------------------------------------

step "Stage 6/6 – Building hybrid ISO with grub-mkrescue"

if [[ $TERMUX_BUILD -eq 1 ]]; then

    # Bind-mount the ISO staging dir and the output directory into the chroot
    # so grub-mkrescue can read the ISO tree and write the output file.
    OUTPUT_DIR="$(dirname "$OUTPUT_ISO")"
    mkdir -p "$OUTPUT_DIR"
    mkdir -p "$ROOTFS/mnt/iso-stage" "$ROOTFS/mnt/iso-out"
    mount --bind "$ISO_STAGE"    "$ROOTFS/mnt/iso-stage"
    mount --bind "$OUTPUT_DIR"   "$ROOTFS/mnt/iso-out"

    OUTPUT_BASENAME="$(basename "$OUTPUT_ISO")"

    chroot "$ROOTFS" /bin/sh -c "
grub-mkrescue \
    --output=/mnt/iso-out/${OUTPUT_BASENAME} \
    --fonts=unicode \
    /mnt/iso-stage \
    -- \
    -volid 'NIGHTMARE-LIVE'
"
    umount "$ROOTFS/mnt/iso-stage" 2>/dev/null || true
    umount "$ROOTFS/mnt/iso-out"   2>/dev/null || true

else

    # --fonts=unicode embeds the unicode.pf2 bitmap font into the image.
    grub-mkrescue \
        --output="$OUTPUT_ISO" \
        --fonts=unicode \
        "$ISO_STAGE" \
        -- \
        -volid "NIGHTMARE-LIVE"

fi

SIZE="$(du -sh "$OUTPUT_ISO" | cut -f1)"

echo
echo -e "${GREEN}============================================================${RESET}"
echo -e "${GREEN} Build complete!${RESET}"
echo
echo "  ISO  : $OUTPUT_ISO"
echo "  Size : $SIZE"
echo
echo " To write to a USB drive:"
echo "   sudo dd if=\"$OUTPUT_ISO\" of=/dev/sdX bs=4M status=progress conv=fsync"
echo
echo " To use from your phone:"
echo "   • EtchDroid (no root): copy the ISO to your phone, plug in a USB"
echo "     drive via OTG, write the ISO, then boot any PC from it."
echo "   • DriveDroid (root required): serve the ISO directly from your phone"
echo "     as a virtual USB drive – no physical USB stick needed."
echo -e "${GREEN}============================================================${RESET}"
