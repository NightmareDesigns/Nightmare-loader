"""
Drive detection, partitioning, and formatting helpers for Nightmare Loader.

Supported layouts
-----------------
``hybrid``  (default / recommended)
    Single FAT32 partition covering the whole device.  Works for both BIOS
    and UEFI.  GRUB legacy BIOS code lives in the MBR gap; the EFI shim lives
    in the FAT32 filesystem as EFI/BOOT/BOOTX64.EFI.

``gpt``
    GPT with two partitions:
      1. Small EFI System Partition (ESP, FAT32, 200 MB)
      2. Data partition (FAT32 or exFAT) for the rest of the drive.

All partitioning is done via ``parted`` and ``mkfs.fat``; these tools must be
available on the host system.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class DriveError(Exception):
    """Raised for drive-related errors."""


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def list_removable_drives() -> list[dict]:
    """
    Return a list of removable block devices (USB drives, etc.).

    Each entry is a dict::

        {
            "device": "/dev/sdb",
            "size":   "16G",
            "model":  "SanDisk Ultra",
            "transport": "usb",
        }

    Requires ``lsblk`` (standard on Linux).
    """
    result = subprocess.run(
        [
            "lsblk",
            "--json",
            "--output",
            "NAME,SIZE,MODEL,TRAN,TYPE,HOTPLUG",
            "--bytes",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DriveError(f"lsblk failed: {result.stderr.strip()}")

    import json
    data = json.loads(result.stdout)
    drives = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        if not dev.get("hotplug"):
            continue
        drives.append(
            {
                "device": f"/dev/{dev['name']}",
                "size": dev.get("size", "?"),
                "model": (dev.get("model") or "").strip(),
                "transport": dev.get("tran", ""),
            }
        )
    return drives


def get_drive_info(device: str) -> dict:
    """Return size and model for a specific block device."""
    result = subprocess.run(
        [
            "lsblk",
            "--json",
            "--output",
            "NAME,SIZE,MODEL,TRAN",
            "--bytes",
            device,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DriveError(f"Cannot read info for {device}: {result.stderr.strip()}")

    import json
    data = json.loads(result.stdout)
    dev = data["blockdevices"][0]
    return {
        "device": device,
        "size": dev.get("size", "?"),
        "model": (dev.get("model") or "").strip(),
        "transport": dev.get("tran", ""),
    }


# ---------------------------------------------------------------------------
# Partitioning / formatting
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    """Run a command, raising DriveError on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DriveError(
            f"Command failed: {' '.join(cmd)}\n{result.stderr.strip()}"
        )


def prepare_drive_hybrid(device: str, label: str = "NIGHTMARE") -> str:
    """
    Wipe and prepare a USB drive with a single FAT32 partition.

    Creates an MBR partition table with one primary FAT32 partition tagged
    as both a regular partition and an EFI system partition so it boots on
    both BIOS and UEFI systems.

    Returns the partition device path (e.g. ``/dev/sdb1``).

    .. warning::
        **This will erase all data on** ``device``.  Confirm with the user
        before calling this function.
    """
    _check_not_mounted(device)

    # Create MBR partition table
    _run(["parted", "-s", device, "mklabel", "msdos"])
    # Single primary partition covering the whole disk
    _run(["parted", "-s", device, "mkpart", "primary", "fat32", "1MiB", "100%"])
    # Mark as bootable
    _run(["parted", "-s", device, "set", "1", "boot", "on"])

    partition = _partition_name(device, 1)
    # Format as FAT32
    _run(["mkfs.fat", "-F32", "-n", label[:11].upper(), partition])
    return partition


def prepare_drive_gpt(device: str, label: str = "NIGHTMARE") -> tuple[str, str]:
    """
    Wipe and prepare a USB drive with a GPT layout:
      1. 200 MiB EFI System Partition (FAT32)
      2. Remaining space as data partition (FAT32)

    Returns ``(esp_partition, data_partition)``, e.g.
    ``("/dev/sdb1", "/dev/sdb2")``.

    .. warning::
        **This will erase all data on** ``device``.
    """
    _check_not_mounted(device)

    _run(["parted", "-s", device, "mklabel", "gpt"])
    _run(["parted", "-s", device, "mkpart", "ESP", "fat32", "1MiB", "201MiB"])
    _run(["parted", "-s", device, "set", "1", "esp", "on"])
    _run(["parted", "-s", device, "mkpart", "DATA", "fat32", "201MiB", "100%"])

    esp = _partition_name(device, 1)
    data = _partition_name(device, 2)
    _run(["mkfs.fat", "-F32", "-n", "EFI", esp])
    _run(["mkfs.fat", "-F32", "-n", label[:11].upper(), data])
    return esp, data


# ---------------------------------------------------------------------------
# Mount helpers
# ---------------------------------------------------------------------------

def mount(partition: str, mount_point: str | Path) -> None:
    """Mount *partition* at *mount_point*, creating the directory if needed."""
    mount_point = Path(mount_point)
    mount_point.mkdir(parents=True, exist_ok=True)
    _run(["mount", partition, str(mount_point)])


def unmount(mount_point: str | Path) -> None:
    """Unmount the filesystem at *mount_point*."""
    _run(["umount", str(mount_point)])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _partition_name(device: str, number: int) -> str:
    """
    Return the partition device node for a given disk and partition number.

    Handles both ``/dev/sdX`` → ``/dev/sdX1`` and
    ``/dev/nvme0n1`` → ``/dev/nvme0n1p1`` style naming.
    """
    if re.search(r"\d$", device):
        # device name ends with a digit (e.g. nvme0n1, mmcblk0) → add 'p'
        return f"{device}p{number}"
    return f"{device}{number}"


def _check_not_mounted(device: str) -> None:
    """Raise DriveError if any partition of *device* is currently mounted."""
    result = subprocess.run(
        ["grep", device, "/proc/mounts"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        raise DriveError(
            f"{device} appears to be mounted. Please unmount it first:\n"
            f"  sudo umount {device}*"
        )
