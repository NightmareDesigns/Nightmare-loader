"""
Known Linux/Windows distribution boot configurations for GRUB2 loopback ISO booting.

Each entry maps a distro key to a dict with:
  - label     : Human-readable menu label (use {version} placeholder when useful)
  - detect    : list of file paths that must exist inside the ISO to trigger detection
  - kernel    : path inside the ISO to the kernel (vmlinuz / live kernel)
  - initrd    : path inside the ISO to the initial ramdisk
  - cmdline   : kernel command-line arguments ({isofile} is replaced at generation time)
"""

from __future__ import annotations

DISTROS: dict[str, dict] = {
    # ---------- Ubuntu / Ubuntu flavours (Casper live system) ----------
    "ubuntu": {
        "label": "Ubuntu",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
    },
    # ---------- Debian live ----------
    "debian": {
        "label": "Debian Live",
        "detect": ["live/vmlinuz", "live/initrd.img"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash ---"
        ),
    },
    # ---------- Fedora / RHEL / CentOS (dracut/live) ----------
    "fedora": {
        "label": "Fedora",
        "detect": ["isolinux/vmlinuz", "isolinux/initrd.img", "LiveOS/squashfs.img"],
        "kernel": "/isolinux/vmlinuz",
        "initrd": "/isolinux/initrd.img",
        "cmdline": (
            "root=live:CDLABEL=LIVE rd.live.image iso-scan/filename={isofile} "
            "quiet rhgb"
        ),
    },
    # ---------- Arch Linux ----------
    "arch": {
        "label": "Arch Linux",
        "detect": ["arch/boot/x86_64/vmlinuz-linux", "arch/boot/x86_64/initramfs-linux.img"],
        "kernel": "/arch/boot/x86_64/vmlinuz-linux",
        "initrd": "/arch/boot/x86_64/initramfs-linux.img",
        "cmdline": (
            "img_dev=/dev/disk/by-label/NIGHTMARE img_loop={isofile} "
            "archisobasedir=arch quiet"
        ),
    },
    # ---------- Manjaro ----------
    "manjaro": {
        "label": "Manjaro",
        "detect": ["manjaro/boot/vmlinuz-x86_64", "manjaro/boot/initramfs-x86_64.img"],
        "kernel": "/manjaro/boot/vmlinuz-x86_64",
        "initrd": "/manjaro/boot/initramfs-x86_64.img",
        "cmdline": (
            "img_dev=/dev/disk/by-label/NIGHTMARE img_loop={isofile} "
            "manjarobasedir=manjaro quiet splash"
        ),
    },
    # ---------- Linux Mint ----------
    "mint": {
        "label": "Linux Mint",
        "detect": ["casper/vmlinuz", "casper/initrd.lz"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd.lz",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
    },
    # ---------- openSUSE (live) ----------
    "opensuse": {
        "label": "openSUSE",
        "detect": ["boot/x86_64/loader/linux", "boot/x86_64/loader/initrd"],
        "kernel": "/boot/x86_64/loader/linux",
        "initrd": "/boot/x86_64/loader/initrd",
        "cmdline": (
            "isofrom_device=usb isofrom_system={isofile} "
            "quiet splash"
        ),
    },
    # ---------- Kali Linux ----------
    "kali": {
        "label": "Kali Linux",
        "detect": ["live/vmlinuz", "live/initrd.img", "live/filesystem.squashfs"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash ---"
        ),
    },
    # ---------- Tails ----------
    "tails": {
        "label": "Tails",
        "detect": ["live/vmlinuz", "live/initrd.img", "live/Tails.module"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash nopersistent"
        ),
    },
    # ---------- Parrot Linux (Debian live) ----------
    "parrot": {
        "label": "Parrot Linux",
        "detect": ["live/vmlinuz", "live/initrd.img", "live/filesystem.module"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash ---"
        ),
    },
    # ---------- Hiren's BootCD PE (WinPE chain-boot) ----------
    "hirens": {
        "label": "Hiren's BootCD PE",
        "detect": ["sources/boot.wim", "bootmgr", "HBCD_PE/PENetwork.ini"],
        "kernel": None,  # WinPE requires a chain-boot approach
        "initrd": None,
        "cmdline": None,
        "note": (
            "Hiren's BootCD PE requires ntfs-3g and a chain-boot shim. "
            "Use the --windows flag when adding this ISO."
        ),
    },
    # ---------- ChromeOS Flex (SysLinux/isolinux loopback boot) ----------
    "chromeos": {
        "label": "ChromeOS Flex",
        "detect": ["syslinux/vmlinuz", "syslinux/initrd.img", "chromeos/"],
        "kernel": "/syslinux/vmlinuz",
        "initrd": "/syslinux/initrd.img",
        "cmdline": (
            "img_loop={isofile} root=/dev/loop0 "
            "quiet splash"
        ),
    },
    # ---------- Windows PE / Windows Setup ----------
    "windows": {
        "label": "Windows",
        "detect": ["sources/boot.wim", "bootmgr"],
        "kernel": None,  # Windows requires a special chain-boot approach
        "initrd": None,
        "cmdline": None,
        "note": (
            "Windows ISOs require ntfs-3g and a chain-boot shim. "
            "Use the --windows flag when adding Windows ISOs."
        ),
    },
    # ---------- Generic fallback ----------
    "generic": {
        "label": "Generic Linux Live",
        "detect": [],
        "kernel": "/boot/vmlinuz",
        "initrd": "/boot/initrd.img",
        "cmdline": "quiet splash",
    },
}


def detect_distro(iso_files: list[str]) -> str:
    """
    Given a list of file paths present inside an ISO, return the best-matching
    distro key from DISTROS.

    Parameters
    ----------
    iso_files:
        List of relative file paths found inside the ISO image (as returned by
        ``iso.list_iso_files``).

    Returns
    -------
    str
        A key from DISTROS (never ``'generic'`` unless nothing else matched).
    """
    # Normalise to forward-slash, lowercase, strip leading slash
    normalised = {f.lstrip("/").lower().replace("\\", "/") for f in iso_files}

    best_key = "generic"
    best_score = -1

    for key, config in DISTROS.items():
        if key == "generic":
            continue
        required = [p.lower() for p in config.get("detect", [])]
        if not required:
            continue
        matched = sum(1 for p in required if p in normalised)
        if matched == 0:
            continue
        score = matched / len(required)
        if score > best_score:
            best_score = score
            best_key = key

    return best_key
