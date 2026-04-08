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
    """
    Linux implementation – uses ``lsblk``.

    A device qualifies as "removable" when:
      • its ``TRAN`` field is ``usb``  (most reliable signal), or
      • its ``HOTPLUG`` attribute is ``1`` (catches some card readers / hubs).

    Vendor and serial number are included when lsblk exposes them so that the
    UI can distinguish two identical-model drives.
    """
    result = subprocess.run(
        [
            "lsblk",
            "--json",
            "--output",
            "NAME,SIZE,MODEL,TRAN,TYPE,HOTPLUG,VENDOR,SERIAL",
            "--bytes",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        # lsblk not available or failed – try the sysfs fallback
        try:
            return _list_removable_drives_sysfs()
        except Exception:
            raise DriveError(f"lsblk failed: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Old lsblk version that doesn't support JSON – use sysfs fallback
        try:
            return _list_removable_drives_sysfs()
        except Exception:
            raise DriveError("lsblk output could not be parsed and sysfs fallback failed.")

    drives = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        tran     = (dev.get("tran") or "").lower()
        hotplug  = dev.get("hotplug") or False
        # Accept USB transport explicitly, or any hotplug-flagged disk
        if tran != "usb" and not hotplug:
            continue
        drives.append(
            {
                "device":    f"/dev/{dev['name']}",
                "size":      dev.get("size", "?"),
                "model":     (dev.get("model") or "").strip(),
                "transport": tran or "usb",
                "vendor":    (dev.get("vendor") or "").strip(),
                "serial":    (dev.get("serial") or "").strip(),
            }
        )
    return drives


def _list_removable_drives_sysfs() -> list[dict]:
    """
    Pure-sysfs fallback for Linux when ``lsblk`` is unavailable or fails.

    Walks ``/sys/block`` and treats any disk-type block device with
    ``removable == 1`` as a candidate.
    """
    sys_block = Path("/sys/block")
    if not sys_block.exists():
        return []

    drives: list[dict] = []
    for dev_dir in sorted(sys_block.iterdir()):
        name = dev_dir.name
        if not (name.startswith("sd") or name.startswith("mmcblk")
                or name.startswith("vd") or name.startswith("ub")):
            continue

        try:
            removable = (dev_dir / "removable").read_text().strip()
        except OSError:
            continue
        if removable != "1":
            continue

        size_bytes = "?"
        try:
            sectors    = int((dev_dir / "size").read_text().strip())
            size_bytes = str(sectors * 512)
        except (OSError, ValueError):
            pass

        model  = ""
        vendor = ""
        for attr, paths in (
            ("model",  [dev_dir / "device" / "model",  dev_dir / "device" / "name"]),
            ("vendor", [dev_dir / "device" / "vendor", dev_dir / "device" / "manufacturer"]),
        ):
            for p in paths:
                try:
                    value = p.read_text().strip()
                    if attr == "model":
                        model  = value
                    else:
                        vendor = value
                    break
                except OSError:
                    continue

        drives.append(
            {
                "device":    f"/dev/{name}",
                "size":      size_bytes,
                "model":     model,
                "transport": "usb",
                "vendor":    vendor,
                "serial":    "",
            }
        )
    return drives


def _list_removable_drives_windows() -> list[dict]:
    """
    Windows implementation – queries removable drives via PowerShell.

    Two strategies are tried in order:

    1. **Storage module** (``Get-Disk`` / ``Get-Partition`` / ``Get-Volume`` –
       Windows 8 / Server 2012 and later).  ``BusType -eq 'USB'`` is the most
       reliable signal for USB flash drives on modern Windows.

    2. **WMI + GetRelated fallback** (works on all Windows versions).  Uses
       the WMI ``GetRelated()`` method to traverse Disk → Partition →
       LogicalDisk, which avoids the backslash-escaping pitfalls of the
       ``ASSOCIATORS OF`` WQL syntax.  Matches on ``InterfaceType -eq 'USB'``,
       ``PNPDeviceID -like 'USBSTOR*'``, or ``MediaType -like '*Removable*'``.

    Returns drives with ``device`` set to the drive-letter root
    (e.g. ``I:\\``).
    """
    # Two-stage PowerShell script.
    # Stage 1 – Storage module (Win 8+ / Server 2012+)
    # Stage 2 – WMI GetRelated fallback (all Windows versions)
    ps_script = (
        "$r = $null; "
        "try { "
        "  $r = @(Get-Disk -ErrorAction Stop "
        "          | Where-Object { $_.BusType -eq 'USB' } "
        "          | ForEach-Object { "
        "              $n = $_.Number; "
        "              $lts = @(Get-Partition -DiskNumber $n -EA SilentlyContinue "
        "                        | Get-Volume -EA SilentlyContinue "
        "                        | Where-Object { $_.DriveLetter } "
        "                        | ForEach-Object { \"$($_.DriveLetter):\" }); "
        "              [PSCustomObject]@{ "
        "                Device  = \"PHYSICALDRIVE$n\"; "
        "                Letters = ($lts -join ','); "
        "                Model   = $_.FriendlyName; "
        "                Size    = $_.Size "
        "              } "
        "          }) "
        "} catch {} "
        "if (-not $r -or $r.Count -eq 0) { "
        "  $r = @(Get-WmiObject Win32_DiskDrive "
        "          | Where-Object { "
        "              $_.InterfaceType -eq 'USB' -or "
        "              $_.PNPDeviceID   -like 'USBSTOR*' -or "
        "              $_.MediaType     -like '*Removable*' "
        "          } "
        "          | ForEach-Object { "
        "              $lts = @($_.GetRelated('Win32_DiskPartition') "
        "                        | ForEach-Object { "
        "                            $_.GetRelated('Win32_LogicalDisk').DeviceID "
        "                          } "
        "                        | Where-Object { $_ }); "
        "              [PSCustomObject]@{ "
        "                Device  = $_.DeviceID; "
        "                Letters = ($lts -join ','); "
        "                Model   = $_.Model; "
        "                Size    = $_.Size "
        "              } "
        "          }) "
        "} "
        "$r | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError:
        raise DriveError("PowerShell not found. Cannot enumerate drives on this system.")
    except subprocess.TimeoutExpired:
        raise DriveError("Drive enumeration timed out.")

    stdout = result.stdout.strip()
    if not stdout or stdout == "[]":
        return []

    raw = json.loads(stdout)
    # PowerShell returns a plain dict (not a list) when there is only one drive
    if isinstance(raw, dict):
        raw = [raw]

    drives = []
    for item in raw:
        letters = item.get("Letters", "")
        # Normalise to a proper Windows drive-letter root (e.g. "E:\").
        # PowerShell may return bare letters ("E"), letters with colon ("E:"),
        # or comma-separated pairs ("E:,F:").  Extract the first usable letter.
        raw_letter = letters.split(",")[0].strip() if letters else ""
        if raw_letter and raw_letter[0].isalpha():
            device = raw_letter[0].upper() + ":\\"
        else:
            device = item.get("Device", "?")
        drives.append(
            {
                "device":    device,
                "size":      str(item.get("Size") or "?"),
                "model":     (item.get("Model") or "").strip(),
                "transport": "usb",
                "vendor":    "",
                "serial":    "",
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
        # Only consider sd*, mmcblk* type devices; skip loop, ram, zram, …
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
                "vendor":    "",
                "serial":    "",
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
