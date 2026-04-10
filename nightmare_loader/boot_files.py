"""
Boot files directory management.

Provides a central location for users to store ISO, WIM, and other bootable files
that can be easily browsed and added to USB drives.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


def get_boot_files_dir() -> Path:
    """
    Get the boot files directory path.

    Default location: ~/.nightmare-loader/boot-files/
    Can be overridden with NIGHTMARE_BOOT_FILES environment variable.

    Returns:
        Path to the boot files directory (created if it doesn't exist)
    """
    env_path = os.environ.get("NIGHTMARE_BOOT_FILES")
    if env_path:
        boot_dir = Path(env_path).expanduser().resolve()
    else:
        boot_dir = Path.home() / ".nightmare-loader" / "boot-files"

    boot_dir.mkdir(parents=True, exist_ok=True)
    return boot_dir


def list_boot_files() -> list[dict]:
    """
    List all bootable files in the boot files directory.

    Returns files with extensions: .iso, .wim, .img

    Returns:
        List of dicts with file info: {name, path, size, extension}
    """
    boot_dir = get_boot_files_dir()
    bootable_extensions = {".iso", ".wim", ".img", ".ISO", ".WIM", ".IMG"}

    files = []
    for item in boot_dir.iterdir():
        if item.is_file() and item.suffix in bootable_extensions:
            files.append({
                "name": item.name,
                "path": str(item),
                "size": item.stat().st_size,
                "extension": item.suffix.lower(),
            })

    # Sort by name
    files.sort(key=lambda x: x["name"].lower())
    return files


def save_uploaded_file(file_data: bytes, filename: str) -> Path:
    """
    Save an uploaded file to the boot files directory.

    Args:
        file_data: Raw file bytes
        filename: Name of the file

    Returns:
        Path to the saved file

    Raises:
        ValueError: If filename has invalid extension
    """
    bootable_extensions = {".iso", ".wim", ".img"}
    file_path = Path(filename)

    if file_path.suffix.lower() not in bootable_extensions:
        raise ValueError(f"Invalid file extension. Supported: {', '.join(bootable_extensions)}")

    boot_dir = get_boot_files_dir()
    dest_path = boot_dir / file_path.name

    # Write the file
    dest_path.write_bytes(file_data)
    return dest_path


def delete_boot_file(filename: str) -> bool:
    """
    Delete a file from the boot files directory.

    Args:
        filename: Name of the file to delete

    Returns:
        True if deleted, False if file didn't exist
    """
    boot_dir = get_boot_files_dir()
    file_path = boot_dir / filename

    if file_path.exists() and file_path.is_file():
        file_path.unlink()
        return True
    return False


def get_boot_file_path(filename: str) -> Optional[Path]:
    """
    Get the full path to a file in the boot files directory.

    Args:
        filename: Name of the file

    Returns:
        Path if file exists, None otherwise
    """
    boot_dir = get_boot_files_dir()
    file_path = boot_dir / filename

    if file_path.exists() and file_path.is_file():
        return file_path
    return None
