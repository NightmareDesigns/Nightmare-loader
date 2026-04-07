#!/bin/sh
# nightmare-live-init.sh
# Custom initramfs init script for the Nightmare Loader live ISO (Alpine path).
#
# Passed to `mkinitfs -i` during the Termux build so this becomes the /init
# inside the generated initramfs.  It replaces Alpine's standard init with a
# minimal live-boot sequence that:
#   1. Mounts proc / sysfs / devtmpfs
#   2. Loads the drivers needed to find and mount the live medium
#   3. Scans block devices for an ISO9660 medium containing
#      /live/filesystem.squashfs (the Nightmare Loader squashfs)
#   4. Mounts the squashfs read-only and layers a writable tmpfs over it
#      via overlayfs so the live session can write to the filesystem freely
#   5. Relocates the virtual filesystems and switch_roots into the new root
#
# Dependencies (provided by mkinitfs "base squashfs" features):
#   busybox (sh, mount, umount, insmod, switch_root, mkdir, echo, ls)
#   squashfs.ko, loop.ko, iso9660.ko, overlay.ko kernel modules

export PATH=/usr/bin:/bin:/sbin:/usr/sbin

# ── Virtual filesystems ──────────────────────────────────────────────────────
mount -t proc     proc     /proc
mount -t sysfs    sysfs    /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts   devpts   /dev/pts

# ── Kernel modules ───────────────────────────────────────────────────────────
# Load modules that live in /lib/modules/ (placed there by mkinitfs from the
# Alpine "squashfs" and "base" feature sets, plus our custom feature.d entries
# for loop, iso9660, and overlay).
for _mod in \
        /lib/modules/loop.ko.gz      /lib/modules/loop.ko \
        /lib/modules/squashfs.ko.gz  /lib/modules/squashfs.ko \
        /lib/modules/isofs.ko.gz     /lib/modules/isofs.ko \
        /lib/modules/overlay.ko.gz   /lib/modules/overlay.ko; do
    [ -f "$_mod" ] && insmod "$_mod" 2>/dev/null || true
done

# ── Locate the Nightmare Loader live medium ──────────────────────────────────
mkdir -p /media

LIVE_DEV=""
# Give udev / kernel a moment to expose block devices
sleep 1

for _dev in /dev/sr0 /dev/sr1 /dev/sda /dev/sdb /dev/sdc /dev/vda; do
    [ -b "$_dev" ] || continue
    mount -t iso9660 -o ro "$_dev" /media 2>/dev/null || continue
    if [ -f /media/live/filesystem.squashfs ]; then
        LIVE_DEV="$_dev"
        break
    fi
    umount /media 2>/dev/null || true
done

if [ -z "$LIVE_DEV" ]; then
    echo "NIGHTMARE LOADER: live medium not found — dropping to emergency shell."
    echo "(mount the ISO and run:  exec switch_root /newroot /sbin/init)"
    exec /bin/sh
fi

# ── Mount squashfs read-only ─────────────────────────────────────────────────
mkdir -p /squash
mount -t squashfs -o ro,loop /media/live/filesystem.squashfs /squash

# ── Overlay: writable tmpfs layer over the squashfs ─────────────────────────
mkdir -p /overlay
mount -t tmpfs -o mode=755 tmpfs /overlay
mkdir -p /overlay/rw /overlay/work /newroot

mount -t overlay overlay \
    -o lowerdir=/squash,upperdir=/overlay/rw,workdir=/overlay/work \
    /newroot

# ── Relocate virtual filesystems into the new root ───────────────────────────
mkdir -p /newroot/proc /newroot/sys /newroot/dev /newroot/dev/pts /newroot/run
mount --move /dev/pts /newroot/dev/pts
mount --move /dev     /newroot/dev
mount --move /proc    /newroot/proc
mount --move /sys     /newroot/sys

# ── Pivot ─────────────────────────────────────────────────────────────────────
exec switch_root /newroot /sbin/init
