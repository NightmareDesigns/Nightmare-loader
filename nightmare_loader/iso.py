"""
ISO utilities: list files inside an ISO, extract metadata, and detect the
contained distribution.
"""

from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from .distros import DISTROS, detect_distro


class ISOError(Exception):
    """Raised when an ISO file cannot be read or is not a valid ISO 9660 image."""


def _isoinfo_available() -> bool:
    """Return True if the ``isoinfo`` binary (from genisoimage/cdrtools) is on PATH."""
    return subprocess.run(
        ["isoinfo", "--version"],
        capture_output=True,
    ).returncode == 0


def list_iso_files(iso_path: str | Path) -> list[str]:
    """
    Return a list of relative file paths contained in an ISO 9660 image.

    Tries ``isoinfo -f`` first (most reliable), then falls back to treating
    the ISO as a ZIP archive (works for some hybrid ISOs), and finally falls
    back to the Python ``zipfile`` module for El Torito images.

    Parameters
    ----------
    iso_path:
        Absolute or relative path to the ``.iso`` file.

    Returns
    -------
    list[str]
        Relative paths of all files found in the image (forward-slash
        separated, no leading slash).

    Raises
    ------
    ISOError
        If the file does not exist or cannot be parsed.
    """
    iso_path = Path(iso_path)
    if not iso_path.exists():
        raise ISOError(f"ISO file not found: {iso_path}")

    # --- attempt isoinfo (preferred) ---
    if _isoinfo_available():
        result = subprocess.run(
            ["isoinfo", "-f", "-i", str(iso_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            # isoinfo lists ISO 9660 paths with a ";1" version suffix.
            # Keep only those lines (they represent real files), then strip
            # the version suffix and leading slashes.
            lines = [
                line.lstrip("/").strip()
                for line in result.stdout.splitlines()
                if line.strip().endswith(";1")
            ]
            cleaned = [ln.split(";")[0].strip("/") for ln in lines if ln]
            return [c for c in cleaned if c]

    # --- fallback: zipfile (some hybrid ISOs are also valid ZIPs) ---
    try:
        with zipfile.ZipFile(iso_path) as zf:
            return [info.filename.rstrip("/") for info in zf.infolist() if not info.is_dir()]
    except (zipfile.BadZipFile, Exception):
        pass

    # --- last resort: return empty list so detect_distro falls back to generic ---
    return []


def get_iso_label(iso_path: str | Path) -> str:
    """
    Return the volume label (disc name) of an ISO image.

    Falls back to the filename stem if the label cannot be determined.
    """
    iso_path = Path(iso_path)
    if _isoinfo_available():
        result = subprocess.run(
            ["isoinfo", "-d", "-i", str(iso_path)],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith("Volume id:"):
                label = line.split(":", 1)[1].strip()
                if label:
                    return label
    return iso_path.stem


def get_iso_metadata(iso_path: str | Path) -> dict:
    """
    Return a metadata dict for the given ISO:

    ``{
        "path": str,
        "filename": str,
        "label": str,
        "size_bytes": int,
        "distro": str,
        "distro_label": str,
        "kernel": str | None,
        "initrd": str | None,
        "cmdline": str | None,
    }``
    """
    iso_path = Path(iso_path)
    files = list_iso_files(iso_path)
    distro_key = detect_distro(files)
    config = DISTROS[distro_key]

    return {
        "path": str(iso_path.resolve()),
        "filename": iso_path.name,
        "label": get_iso_label(iso_path),
        "size_bytes": iso_path.stat().st_size,
        "distro": distro_key,
        "distro_label": config["label"],
        "kernel": config.get("kernel"),
        "initrd": config.get("initrd"),
        "cmdline": config.get("cmdline"),
        "boot_type": config.get("boot_type", ""),
    }
