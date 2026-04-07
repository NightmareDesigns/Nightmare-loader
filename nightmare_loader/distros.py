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
        "download_url": (
            "https://releases.ubuntu.com/24.04.1/"
            "ubuntu-24.04.1-desktop-amd64.iso"
        ),
        "download_size_mb": 5800,
    },
    # ---------- Ubuntu 22.04 LTS ----------
    "ubuntu-22": {
        "label": "Ubuntu 22.04 LTS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://releases.ubuntu.com/22.04.5/"
            "ubuntu-22.04.5-desktop-amd64.iso"
        ),
        "download_size_mb": 4700,
    },
    # ---------- Kubuntu ----------
    "kubuntu": {
        "label": "Kubuntu 24.04 LTS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://cdimage.ubuntu.com/kubuntu/releases/24.04.1/release/"
            "kubuntu-24.04.1-desktop-amd64.iso"
        ),
        "download_size_mb": 3900,
    },
    # ---------- Xubuntu ----------
    "xubuntu": {
        "label": "Xubuntu 24.04 LTS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://cdimage.ubuntu.com/xubuntu/releases/24.04/release/"
            "xubuntu-24.04-desktop-amd64.iso"
        ),
        "download_size_mb": 3200,
    },
    # ---------- Lubuntu ----------
    "lubuntu": {
        "label": "Lubuntu 24.04 LTS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://cdimage.ubuntu.com/lubuntu/releases/24.04/release/"
            "lubuntu-24.04-desktop-amd64.iso"
        ),
        "download_size_mb": 2800,
    },
    # ---------- Ubuntu Studio ----------
    "ubuntu-studio": {
        "label": "Ubuntu Studio 24.04 LTS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://cdimage.ubuntu.com/ubuntustudio/releases/24.04/release/"
            "ubuntustudio-24.04-dvd-amd64.iso"
        ),
        "download_size_mb": 4800,
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
        "download_url": (
            "https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/"
            "debian-live-12.9.0-amd64-gnome.iso"
        ),
        "download_size_mb": 3200,
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
        "download_url": (
            "https://download.fedoraproject.org/pub/fedora/linux/releases/41/"
            "Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-41-1.4.iso"
        ),
        "download_size_mb": 2200,
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
        "download_url": (
            "https://mirror.rackspace.com/archlinux/iso/latest/"
            "archlinux-x86_64.iso"
        ),
        "download_size_mb": 900,
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
        "download_url": (
            "https://download.manjaro.org/gnome/24.2.1/"
            "manjaro-gnome-24.2.1-241216-linux612.iso"
        ),
        "download_size_mb": 4200,
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
        "download_url": (
            "https://mirrors.layeronline.com/linuxmint/stable/22.1/"
            "linuxmint-22.1-cinnamon-64bit.iso"
        ),
        "download_size_mb": 2800,
    },
    # ---------- Linux Mint MATE ----------
    "mint-mate": {
        "label": "Linux Mint MATE",
        "detect": ["casper/vmlinuz", "casper/initrd.lz"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd.lz",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://mirrors.layeronline.com/linuxmint/stable/22.1/"
            "linuxmint-22.1-mate-64bit.iso"
        ),
        "download_size_mb": 2800,
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
        "download_url": (
            "https://download.opensuse.org/distribution/leap/15.6/live/"
            "openSUSE-Leap-15.6-GNOME-Live-x86_64.iso"
        ),
        "download_size_mb": 1200,
    },
    # ---------- openSUSE Tumbleweed ----------
    "opensuse-tw": {
        "label": "openSUSE Tumbleweed",
        "detect": ["boot/x86_64/loader/linux", "boot/x86_64/loader/initrd"],
        "kernel": "/boot/x86_64/loader/linux",
        "initrd": "/boot/x86_64/loader/initrd",
        "cmdline": (
            "isofrom_device=usb isofrom_system={isofile} "
            "quiet splash"
        ),
        "download_url": (
            "https://download.opensuse.org/tumbleweed/iso/"
            "openSUSE-Tumbleweed-GNOME-Live-x86_64-Current.iso"
        ),
        "download_size_mb": 1300,
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
        "download_url": (
            "https://cdimage.kali.org/kali-2024.4/"
            "kali-linux-2024.4-live-amd64.iso"
        ),
        "download_size_mb": 4100,
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
        "download_url": (
            "https://mirrors.edge.kernel.org/tails/stable/tails-amd64-6.11/"
            "tails-amd64-6.11.iso"
        ),
        "download_size_mb": 1300,
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
        "download_url": (
            "https://download.parrot.sh/parrot/iso/6.3/"
            "Parrot-security-6.3_amd64.iso"
        ),
        "download_size_mb": 5100,
    },
    # ---------- Parrot Home Edition ----------
    "parrot-home": {
        "label": "Parrot Home",
        "detect": ["live/vmlinuz", "live/initrd.img", "live/filesystem.module"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://download.parrot.sh/parrot/iso/6.3/"
            "Parrot-home-6.3_amd64.iso"
        ),
        "download_size_mb": 2400,
    },
    # ---------- BlackArch Linux ----------
    "blackarch": {
        "label": "BlackArch Linux",
        "detect": ["arch/boot/x86_64/vmlinuz-linux", "arch/boot/x86_64/initramfs-linux.img"],
        "kernel": "/arch/boot/x86_64/vmlinuz-linux",
        "initrd": "/arch/boot/x86_64/initramfs-linux.img",
        "cmdline": (
            "img_dev=/dev/disk/by-label/NIGHTMARE img_loop={isofile} "
            "archisobasedir=arch quiet"
        ),
        "download_url": (
            "https://ftp.halifax.rwth-aachen.de/blackarch/iso/blackarch-linux-full-2024.01.01-x86_64.iso"
        ),
        "download_size_mb": 20000,
    },
    # ---------- Whonix (Gateway + Workstation) ----------
    "whonix": {
        "label": "Whonix",
        "detect": ["live/vmlinuz", "live/initrd.img"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://download.whonix.org/ova/17.2.3.7/"
            "Whonix-XFCE-17.2.3.7.iso"
        ),
        "download_size_mb": 1900,
    },
    # ---------- Zorin OS ----------
    "zorin": {
        "label": "Zorin OS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://mirror.zorin.com/zorin-os/zorin-os-17-core-64-bit.iso"
        ),
        "download_size_mb": 3500,
    },
    # ---------- Pop!_OS ----------
    "popos": {
        "label": "Pop!_OS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://iso.pop-os.org/22.04/amd64/intel/42/"
            "pop-os_22.04_amd64_intel_42.iso"
        ),
        "download_size_mb": 2600,
    },
    # ---------- elementary OS ----------
    "elementary": {
        "label": "elementary OS",
        "detect": ["casper/vmlinuz", "casper/initrd"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://sgp1.dl.elementary.io/download/MTcxNzYxMzAzMg==/"
            "elementaryos-8.0-stable.20240501.iso"
        ),
        "download_size_mb": 2900,
    },
    # ---------- MX Linux ----------
    "mxlinux": {
        "label": "MX Linux",
        "detect": ["live/vmlinuz", "live/initrd.img"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://sourceforge.net/projects/mx-linux/files/Final/Xfce/"
            "MX-23.5_x64.iso"
        ),
        "download_size_mb": 1900,
    },
    # ---------- EndeavourOS ----------
    "endeavouros": {
        "label": "EndeavourOS",
        "detect": ["arch/boot/x86_64/vmlinuz-linux", "arch/boot/x86_64/initramfs-linux.img"],
        "kernel": "/arch/boot/x86_64/vmlinuz-linux",
        "initrd": "/arch/boot/x86_64/initramfs-linux.img",
        "cmdline": (
            "img_dev=/dev/disk/by-label/NIGHTMARE img_loop={isofile} "
            "archisobasedir=arch quiet"
        ),
        "download_url": (
            "https://mirror.alpix.eu/endeavouros/iso/"
            "EndeavourOS_Gemini-2024.09.22.iso"
        ),
        "download_size_mb": 2800,
    },
    # ---------- Garuda Linux ----------
    "garuda": {
        "label": "Garuda Linux",
        "detect": ["arch/boot/x86_64/vmlinuz-linux", "arch/boot/x86_64/initramfs-linux.img"],
        "kernel": "/arch/boot/x86_64/vmlinuz-linux",
        "initrd": "/arch/boot/x86_64/initramfs-linux.img",
        "cmdline": (
            "img_dev=/dev/disk/by-label/NIGHTMARE img_loop={isofile} "
            "archisobasedir=arch quiet"
        ),
        "download_url": (
            "https://iso.builds.garudalinux.org/iso/latest/garuda/dr460nized/"
            "garuda-dr460nized-linux-zen-current.iso"
        ),
        "download_size_mb": 3100,
    },
    # ---------- Hiren's BootCD PE (WinPE – full Windows 10/11 repair suite) ----------
    "hirens": {
        "label": "Hiren's BootCD PE",
        "detect": ["sources/boot.wim", "bootmgr", "HBCD_PE/PENetwork.ini"],
        "kernel": None,
        "initrd": None,
        "cmdline": None,
        "boot_type": "winpe",
        "note": (
            "Hiren's BootCD PE boots a full Windows 11 PE environment with "
            "100+ repair tools including: NirSoft registry editor & viewer, "
            "password reset, antivirus, MiniTool Partition Wizard, HWiNFO, "
            "and a full command prompt for bootrec/sfc/chkdsk. "
            "Download manually from https://www.hirensbootcd.org/download/"
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
        "kernel": None,
        "initrd": None,
        "cmdline": None,
        "boot_type": "winpe",
        "note": (
            "Windows ISOs are detected as 'windows' and use EFI chain-boot "
            "on UEFI systems. Boot the official Windows ISO and choose "
            "'Repair your computer' to access the standard Windows recovery "
            "tools (Startup Repair, System Restore, Command Prompt)."
        ),
    },
    # ---------- Rescuezilla (Ubuntu/Casper – disk imaging & Windows repair) ----------
    "rescuezilla": {
        "label": "Rescuezilla",
        "detect": ["rescuezilla", "casper/vmlinuz"],
        "kernel": "/casper/vmlinuz",
        "initrd": "/casper/initrd",
        "cmdline": (
            "boot=casper iso-scan/filename={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://github.com/rescuezilla/rescuezilla/releases/download/2.5.1/"
            "rescuezilla-2.5.1-64bit.noble.iso"
        ),
        "download_size_mb": 780,
    },
    # ---------- SystemRescue (Arch-based, chntpw / ntfs-3g / Windows repair) ----------
    "systemrescue": {
        "label": "SystemRescue",
        "detect": ["sysresccd/boot/x86_64/vmlinuz", "sysresccd/boot/x86_64/sysresccd.img"],
        "kernel": "/sysresccd/boot/x86_64/vmlinuz",
        "initrd": "/sysresccd/boot/x86_64/sysresccd.img",
        "cmdline": (
            "img_dev=/dev/disk/by-label/NIGHTMARE img_loop={isofile} "
            "archisobasedir=sysresccd quiet"
        ),
        "download_url": (
            "https://fastly-cdn.system-rescue.org/releases/11.02/"
            "systemrescue-11.02-amd64.iso"
        ),
        "download_size_mb": 800,
    },
    # ---------- GParted Live (Debian live – partition editing) ----------
    "gparted": {
        "label": "GParted Live",
        "detect": ["live/vmlinuz", "live/initrd.img", "live/filesystem.squashfs",
                   "utils/linux/grub2/grub.cfg"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet splash ---"
        ),
        "download_url": (
            "https://downloads.sourceforge.net/gparted/"
            "gparted-live-1.6.0-3-amd64.iso"
        ),
        "download_size_mb": 600,
    },
    # ---------- Clonezilla Live (Debian live – disk backup/restore) ----------
    "clonezilla": {
        "label": "Clonezilla Live",
        "detect": ["live/vmlinuz", "live/initrd.img", "live/filesystem.squashfs",
                   "utils/grub2/grub.cfg"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} union=overlay "
            "quiet splash ---"
        ),
        "download_url": (
            "https://sourceforge.net/projects/clonezilla/files/clonezilla_live_stable/"
            "3.1.2-22/clonezilla-live-3.1.2-22-amd64.iso"
        ),
        "download_size_mb": 450,
    },
    # ---------- Memtest86+ (EFI/legacy RAM tester – chain-boot) ----------
    "memtest86plus": {
        "label": "Memtest86+",
        "detect": ["EFI/BOOT/memtest.efi"],
        "kernel": None,
        "initrd": None,
        "cmdline": None,
        "boot_type": "winpe",
        "note": (
            "Memtest86+ is an EFI application booted via EFI chain-boot. "
            "Tests all RAM banks for hardware errors."
        ),
        "download_url": (
            "https://www.memtest.org/download/v7.20/mt86plus_7.20_64.iso"
        ),
        "download_size_mb": 15,
    },
    # ---------- ShredOS (Debian live – secure disk wipe) ----------
    "shredos": {
        "label": "ShredOS",
        "detect": ["live/vmlinuz", "live/initrd.img", "shredos"],
        "kernel": "/live/vmlinuz",
        "initrd": "/live/initrd.img",
        "cmdline": (
            "boot=live findiso={isofile} "
            "quiet ---"
        ),
        "download_url": (
            "https://github.com/PartialVolume/shredos.x86_64/releases/download/"
            "v2024.02.2_26_x86_64_0.38.027/shredos-2024.02.2_26_x86_64_0.38.027.img"
        ),
        "download_size_mb": 30,
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


# ---------------------------------------------------------------------------
# Curated 64 GB kit
# ---------------------------------------------------------------------------

# Each entry is (distro_key, approximate_size_mb, category, short_description).
# Total is kept under 58 000 MB (~57 GB) to leave room for FAT32 overhead and
# the Windows ISOs that the user must download manually from Microsoft.
KIT_64GB: list[tuple[str, int, str, str]] = [
    # ── Windows repair (manual download – add these yourself) ──────────────
    # win11-repair   ~5800 MB  (download from microsoft.com)
    # win10-repair   ~4700 MB  (download from microsoft.com)
    # hirens         ~700 MB   (download from hirensbootcd.org)

    # ── Auto-downloadable repair & recovery tools (~2 275 MB) ──────────────
    ("rescuezilla",   780,  "repair",  "Graphical disk/file recovery & Windows repair"),
    ("systemrescue",  800,  "repair",  "CLI toolkit: chntpw, ntfsfix, testdisk, photorec"),
    ("gparted",       600,  "repair",  "Partition resize, repair, and management"),
    ("clonezilla",    450,  "repair",  "Full-disk backup and bare-metal restore"),
    ("memtest86plus",  15,  "repair",  "RAM hardware diagnostic"),
    ("shredos",        30,  "repair",  "Secure drive wipe (nwipe)"),

    # ── General-purpose desktop Linux (~8 300 MB) ──────────────────────────
    ("ubuntu",       5800,  "desktop", "Ubuntu 24.04 LTS – daily driver"),
    ("mint",         2800,  "desktop", "Linux Mint 22.1 Cinnamon – Windows-like desktop"),
    ("fedora",       2200,  "desktop", "Fedora 41 Workstation – cutting-edge Linux"),

    # ── Lightweight / recovery Linux (~4 300 MB) ───────────────────────────
    ("debian",       3200,  "desktop", "Debian Live 12 – rock-solid base OS"),
    ("mxlinux",      1900,  "desktop", "MX Linux – fast, great live-boot tools"),

    # ── Security & privacy (~6 700 MB) ────────────────────────────────────
    ("kali",         4100,  "security","Kali Linux – penetration testing"),
    ("tails",        1300,  "security","Tails – anonymous, amnesic OS"),
    ("parrot-home",  2400,  "security","Parrot Home – privacy-focused desktop"),

    # ── Arch-based advanced (~1 800 MB) ───────────────────────────────────
    ("arch",          900,  "advanced","Arch Linux – bleeding edge, minimal"),
    ("endeavouros",  2800,  "advanced","EndeavourOS – Arch with a friendly installer"),
]

# Running total of auto-downloadable items (MB)
KIT_64GB_AUTO_MB: int = sum(size for _, size, _, _ in KIT_64GB)



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
