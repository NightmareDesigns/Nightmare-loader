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

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


class DriveError(Exception):
    """Raised for drive-related errors."""


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def _is_termux() -> bool:
    """Return True when running inside the Termux Android terminal emulator."""
    # Termux sets TERMUX_VERSION; alternatively its prefix is always /data/data/com.termux
    if os.environ.get("TERMUX_VERSION"):
        return True
    return Path("/data/data/com.termux").exists()


def list_removable_drives() -> list[dict]:
    """
    Return a list of removable block devices (USB drives, etc.).

    Each entry is a dict::

        {
            "device": "/dev/sdb",        # Linux/Android – or "D:\\" on Windows
            "size":   "16000000000",     # bytes as string
            "model":  "SanDisk Ultra",
            "transport": "usb",
        }

    Dispatches to a platform-specific implementation.
    """
    if sys.platform == "win32":
        return _list_removable_drives_windows()
    if _is_termux():
        return _list_removable_drives_android()
    return _list_removable_drives_linux()


def _list_removable_drives_linux() -> list[dict]:
    """Linux implementation – uses ``lsblk``."""
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


def _list_removable_drives_windows() -> list[dict]:
    """
    Windows implementation – queries removable drives via PowerShell/WMI.

    Returns drives with ``device`` set to the drive letter (e.g. ``D:\\``).
    Disk partitioning operations (prepare/add/remove) are not supported on
    Windows; the list lets the web UI inspect ISOs on an already-prepared USB.
    """
    ps_script = (
        "Get-WmiObject Win32_DiskDrive "
        "| Where-Object { $_.MediaType -like '*Removable*' -or $_.InterfaceType -eq 'USB' } "
        "| ForEach-Object { "
        "    $d = $_; "
        "    $letters = @(Get-WmiObject -Query "
        "        \"ASSOCIATORS OF {Win32_DiskDrive.DeviceID='$(($d.DeviceID -replace '\\\\','\\\\\\\\'))'} "
        "        WHERE AssocClass=Win32_DiskDriveToDiskPartition\" "
        "        | ForEach-Object { (Get-WmiObject -Query "
        "            \"ASSOCIATORS OF {Win32_DiskPartition.DeviceID='$($_.DeviceID)'} "
        "            WHERE AssocClass=Win32_LogicalDiskToPartition\").DeviceID }); "
        "    [PSCustomObject]@{ Device=$d.DeviceID; Letters=($letters -join ','); "
        "        Model=$d.Model; Size=$d.Size } "
        "} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        raise DriveError("PowerShell not found. Cannot enumerate drives on this system.")
    except subprocess.TimeoutExpired:
        raise DriveError("Drive enumeration timed out.")

    stdout = result.stdout.strip()
    if not stdout:
        return []

    raw = json.loads(stdout)
    # PowerShell returns a single object (not a list) when there is only one drive
    if isinstance(raw, dict):
        raw = [raw]

    drives = []
    for item in raw:
        letters = item.get("Letters", "")
        # Use the first drive letter as the device path; fall back to DeviceID
        device = (letters.split(",")[0].strip() + "\\") if letters else item.get("Device", "?")
        drives.append(
            {
                "device":    device,
                "size":      str(item.get("Size") or "?"),
                "model":     (item.get("Model") or "").strip(),
                "transport": "usb",
            }
        )
    return drives


def _list_removable_drives_android() -> list[dict]:
    """
    Android/Termux implementation – walks ``/sys/block`` sysfs entries.

    On Android the kernel exposes block devices under ``/sys/block``.
    A device is considered removable when its ``removable`` sysfs attribute
    is ``1``.  OTG USB storage typically appears as ``sd*``; the size is read
    from the ``size`` attribute (512-byte sectors).

    Disk partitioning operations (prepare/add/remove) require root access
    and the ``parted`` / ``mkfs.fat`` packages from Termux.  The list is
    still useful for ISO inspection on an already-prepared USB drive.
    """
    sys_block = Path("/sys/block")
    if not sys_block.exists():
        return []

    drives: list[dict] = []
    for dev_dir in sorted(sys_block.iterdir()):
        name = dev_dir.name
        # Only consider sd* and mmcblk* type devices; skip loop, ram, zram, …
        if not (name.startswith("sd") or name.startswith("mmcblk")):
            continue

        removable_file = dev_dir / "removable"
        try:
            removable = removable_file.read_text().strip()
        except OSError:
            continue
        if removable != "1":
            continue

        # Read size (in 512-byte sectors)
        size_bytes: str = "?"
        size_file = dev_dir / "size"
        try:
            sectors = int(size_file.read_text().strip())
            size_bytes = str(sectors * 512)
        except (OSError, ValueError):
            pass

        # Read model (may not exist for all devices)
        model = ""
        for model_path in (dev_dir / "device" / "model", dev_dir / "device" / "name"):
            try:
                model = model_path.read_text().strip()
                break
            except OSError:
                continue

        drives.append(
            {
                "device":    f"/dev/{name}",
                "size":      size_bytes,
                "model":     model,
                "transport": "usb",
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
