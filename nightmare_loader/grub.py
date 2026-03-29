"""
GRUB2 bootloader configuration and installation helpers.

Supports:
  - Legacy BIOS (i386-pc target)
  - UEFI  (x86_64-efi target)
  - Config generation with loopback ISO entries
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Config file paths (relative to the mount-point / root of the USB drive)
# ---------------------------------------------------------------------------
GRUB_DIR = "boot/grub"
GRUB_CFG = f"{GRUB_DIR}/grub.cfg"
ISO_DIR = "isos"
STATE_FILE = ".nightmare-loader.json"

# GRUB modules needed for both legacy and EFI targets
GRUB_MODULES = [
    "part_gpt",
    "part_msdos",
    "fat",
    "iso9660",
    "loopback",
    "linux",
    "normal",
    "configfile",
    "all_video",
    "gfxterm",
    "png",
    "echo",
    "cat",
    "reboot",
    "halt",
]

# ---------------------------------------------------------------------------
# Menu colour / theme defaults
# ---------------------------------------------------------------------------
_HEADER = """\
# Nightmare Loader – GRUB2 multi-ISO boot menu
# Auto-generated – do not edit by hand; use nightmare-loader to manage ISOs.

set default=0
set timeout=10

insmod part_gpt
insmod part_msdos
insmod fat
insmod iso9660
insmod loopback
insmod linux
insmod all_video
insmod gfxterm

set gfxmode=auto
terminal_output gfxterm

"""

_FOOTER = """
menuentry "Reboot" {
    reboot
}

menuentry "Power Off" {
    halt
}
"""


def _linux_entry(label: str, isofile: str, kernel: str, initrd: str, cmdline: str) -> str:
    """Generate a single GRUB menuentry that loopback-mounts an ISO."""
    # isofile should be the path as seen by GRUB, e.g. /isos/ubuntu.iso
    filled_cmdline = cmdline.format(isofile=isofile)
    return textwrap.dedent(f"""\
        menuentry "{label}" {{
            set isofile="{isofile}"
            loopback loop "$isofile"
            linux (loop){kernel} {filled_cmdline}
            initrd (loop){initrd}
        }}
        """)


def _windows_entry(label: str, isofile: str) -> str:
    """
    Generate a GRUB menuentry for a Windows ISO.

    Uses the ``ntldr`` / ``chainloader`` approach: we chain into the Windows
    boot manager after mapping the ISO as a virtual disk via the ``img_mount``
    command.  This requires the ``wimboot`` kernel to be installed alongside
    GRUB (copy wimboot to /boot/grub/wimboot on the USB stick).
    """
    return textwrap.dedent(f"""\
        menuentry "{label} (Windows – requires wimboot)" {{
            set isofile="{isofile}"
            loopback loop "$isofile"
            # Load wimboot to handle WIM-based Windows setup
            linux16 /boot/grub/wimboot
            initrd16 \
                newc:bootmgr:(loop)/bootmgr \
                newc:bcd:(loop)/Boot/BCD \
                newc:boot.sdi:(loop)/Boot/boot.sdi \
                newc:boot.wim:(loop)/sources/boot.wim
        }}
        """)


def generate_grub_cfg(entries: list[dict]) -> str:
    """
    Generate a complete grub.cfg string from a list of ISO entry dicts.

    Each entry dict is the metadata dict produced by
    ``iso.get_iso_metadata``, enriched with an ``isofile`` key that holds
    the GRUB-side path to the ISO (e.g. ``/isos/ubuntu.iso``).

    Parameters
    ----------
    entries:
        List of entry dicts.  Expected keys: ``label``, ``isofile``,
        ``distro``, ``kernel``, ``initrd``, ``cmdline``.

    Returns
    -------
    str
        Full grub.cfg file content.
    """
    parts = [_HEADER]
    for entry in entries:
        distro = entry.get("distro", "generic")
        label = entry.get("label", entry.get("distro_label", entry.get("filename", "Unknown")))
        isofile = entry["isofile"]
        kernel = entry.get("kernel")
        initrd = entry.get("initrd")
        cmdline = entry.get("cmdline", "quiet splash")

        if distro == "windows" or (kernel is None and initrd is None):
            # Windows ISOs and any entry whose distro config has kernel=None /
            # initrd=None intentionally use the wimboot chain-boot path instead
            # of the standard linux/initrd loopback approach.
            parts.append(_windows_entry(label, isofile))
        else:
            parts.append(_linux_entry(label, isofile, kernel, initrd, cmdline))

    parts.append(_FOOTER)
    return "\n".join(parts)


def write_grub_cfg(mount_point: str | Path, entries: list[dict]) -> Path:
    """
    Write grub.cfg to ``<mount_point>/boot/grub/grub.cfg``.

    Returns the path to the written file.
    """
    mount_point = Path(mount_point)
    cfg_path = mount_point / GRUB_CFG
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(generate_grub_cfg(entries))
    return cfg_path


def install_grub_bios(device: str, mount_point: str | Path) -> None:
    """
    Install GRUB2 for legacy BIOS boot onto *device*.

    Parameters
    ----------
    device:
        Block device path, e.g. ``/dev/sdb``.
    mount_point:
        Path where the device's main partition is mounted.
    """
    subprocess.run(
        [
            "grub-install",
            "--target=i386-pc",
            f"--boot-directory={Path(mount_point) / 'boot'}",
            "--recheck",
            device,
        ],
        check=True,
    )


def install_grub_efi(mount_point: str | Path, removable: bool = True) -> None:
    """
    Install GRUB2 for UEFI boot.

    Parameters
    ----------
    mount_point:
        Path where the EFI System Partition (ESP) is mounted (or the combined
        partition in the case of a hybrid USB).
    removable:
        If True, installs to the removable media fallback path
        (``EFI/BOOT/BOOTX64.EFI``), which is required for USB sticks that
        will be used on machines that don't have a persistent NVRAM entry.
    """
    cmd = [
        "grub-install",
        "--target=x86_64-efi",
        f"--efi-directory={mount_point}",
        f"--boot-directory={Path(mount_point) / 'boot'}",
        "--recheck",
    ]
    if removable:
        cmd.append("--removable")
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# State persistence (tracks which ISOs are registered on a drive)
# ---------------------------------------------------------------------------

def _state_path(mount_point: str | Path) -> Path:
    return Path(mount_point) / STATE_FILE


def load_state(mount_point: str | Path) -> dict:
    """Load the Nightmare Loader state JSON from the drive root."""
    path = _state_path(mount_point)
    if path.exists():
        return json.loads(path.read_text())
    return {"entries": []}


def save_state(mount_point: str | Path, state: dict) -> None:
    """Persist the Nightmare Loader state JSON to the drive root."""
    _state_path(mount_point).write_text(json.dumps(state, indent=2))
