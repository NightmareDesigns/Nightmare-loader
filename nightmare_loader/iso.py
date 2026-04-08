"""
ISO utilities: list files inside an ISO, extract metadata, and detect the
contained distribution.

File-listing strategy (tried in order until one succeeds):
  1. isoinfo -f          (genisoimage / cdrtools – most accurate for ISO 9660)
  2. 7z / 7za / 7zz l   (p7zip – handles UDF and hybrid ISOs)
  3. zipfile             (pure Python – works for El Torito / hybrid ZIPs)
  4. []                  (empty – detect_distro falls back to "generic")

Volume-label strategy (tried in order until one succeeds):
  1. Pure-Python ISO 9660 PVD reader (no external tools required)
  2. blkid -o value -s LABEL (Linux only, fast)
  3. isoinfo -d
  4. filename stem
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

from .distros import DISTROS, detect_distro


class ISOError(Exception):
    """Raised when an ISO file cannot be read or is not a valid ISO 9660 image."""


# ---------------------------------------------------------------------------
# Tool availability helpers
# ---------------------------------------------------------------------------

def _isoinfo_available() -> bool:
    """Return True if the ``isoinfo`` binary (from genisoimage/cdrtools) is on PATH."""
    try:
        return subprocess.run(
            ["isoinfo", "--version"],
            capture_output=True,
        ).returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _7z_cmd() -> str | None:
    """Return the name of the first available 7-Zip binary, or None."""
    for cmd in ("7z", "7za", "7zz"):
        if shutil.which(cmd):
            return cmd
    return None


# ---------------------------------------------------------------------------
# Pure-Python ISO 9660 Primary Volume Descriptor reader
# ---------------------------------------------------------------------------

_ISO_SECTOR = 2048
_PVD_SECTOR = 16          # PVD is always at sector 16
_CD001      = b"CD001"    # ISO 9660 magic


def _read_pvd(iso_path: Path) -> bytes:
    """
    Read the 2048-byte Primary Volume Descriptor sector from an ISO image.

    Raises ISOError if the file is too small or lacks the CD001 signature.
    """
    try:
        with open(iso_path, "rb") as fh:
            fh.seek(_PVD_SECTOR * _ISO_SECTOR)
            pvd = fh.read(_ISO_SECTOR)
    except OSError as exc:
        raise ISOError(f"Cannot read ISO file: {exc}") from exc

    if len(pvd) < 190:
        raise ISOError(f"File too small to be a valid ISO image: {iso_path}")
    if pvd[1:6] != _CD001:
        raise ISOError(f"Not a valid ISO 9660 image (missing CD001 signature): {iso_path}")
    return pvd


def _pvd_label(pvd: bytes) -> str:
    """Extract the Volume Identifier from a PVD byte string (bytes 40–71)."""
    raw = pvd[40:72]
    # Try UTF-8 first; fall back to latin-1 which never fails
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc).rstrip()
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace").rstrip()


# ---------------------------------------------------------------------------
# File listing
# ---------------------------------------------------------------------------

def list_iso_files(iso_path: str | Path) -> list[str]:
    """
    Return a list of relative file paths contained in an ISO 9660 image.

    The function tries multiple backends in order and returns the first
    successful result.  If all backends fail the empty list is returned so
    that :func:`detect_distro` can fall back gracefully to ``"generic"``.

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
        If the file does not exist.
    """
    iso_path = Path(iso_path).resolve()
    if not iso_path.exists():
        raise ISOError(f"ISO file not found: {iso_path}")

    # Verify it looks like an ISO before spending time on heavier tools
    try:
        _read_pvd(iso_path)
    except ISOError:
        pass  # Let the tools below give a more informative error if they fail

    # 1. isoinfo (most accurate for ISO 9660 Joliet/Rock Ridge)
    if _isoinfo_available():
        result = subprocess.run(
            ["isoinfo", "-f", "-i", str(iso_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = [
                line.lstrip("/").strip()
                for line in result.stdout.splitlines()
                if line.strip().endswith(";1")
            ]
            cleaned = [ln.split(";")[0].strip("/") for ln in lines if ln]
            files = [c for c in cleaned if c]
            if files:
                return files

    # 2. 7z / 7za / 7zz  (handles UDF, hybrid, and El Torito)
    cmd_7z = _7z_cmd()
    if cmd_7z:
        result = subprocess.run(
            [cmd_7z, "l", "-ba", "-slt", str(iso_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            files = []
            for line in result.stdout.splitlines():
                if line.startswith("Path = "):
                    p = line[7:].strip().lstrip("/").replace("\\", "/")
                    if p:
                        files.append(p)
            if files:
                return files

    # 3. zipfile (pure Python – works for some hybrid ISOs that are also ZIPs)
    try:
        with zipfile.ZipFile(iso_path) as zf:
            names = [
                info.filename.rstrip("/")
                for info in zf.infolist()
                if not info.is_dir()
            ]
            if names:
                return names
    except (zipfile.BadZipFile, Exception):
        pass

    # 4. Empty list – detect_distro will fall back to "generic"
    return []


# ---------------------------------------------------------------------------
# Volume label
# ---------------------------------------------------------------------------

def get_iso_label(iso_path: str | Path) -> str:
    """
    Return the volume label (disc name) of an ISO image.

    Falls back to the filename stem if the label cannot be determined.
    """
    iso_path = Path(iso_path).resolve()

    # 1. Pure-Python PVD read (works with zero external tools)
    try:
        pvd = _read_pvd(iso_path)
        label = _pvd_label(pvd)
        if label:
            return label
    except ISOError:
        pass

    # 2. blkid (Linux; fast, handles UDF labels that isoinfo misses)
    if shutil.which("blkid"):
        try:
            result = subprocess.run(
                ["blkid", "-o", "value", "-s", "LABEL", str(iso_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            label = result.stdout.strip()
            if label:
                return label
        except Exception:
            pass

    # 3. isoinfo -d
    if _isoinfo_available():
        try:
            result = subprocess.run(
                ["isoinfo", "-d", "-i", str(iso_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in result.stdout.splitlines():
                if line.strip().startswith("Volume id:"):
                    label = line.split(":", 1)[1].strip()
                    if label:
                        return label
        except Exception:
            pass

    # 4. Fall back to filename stem
    return iso_path.stem


# ---------------------------------------------------------------------------
# Metadata bundle
# ---------------------------------------------------------------------------

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
    iso_path = Path(iso_path).resolve()
    if not iso_path.exists():
        raise ISOError(f"ISO file not found: {iso_path}")

    files      = list_iso_files(iso_path)
    distro_key = detect_distro(files)
    config     = DISTROS[distro_key]

    # get_iso_label now uses the fast pure-Python PVD path first, so calling
    # it here does not duplicate work from list_iso_files.
    return {
        "path":         str(iso_path.resolve()),
        "filename":     iso_path.name,
        "label":        get_iso_label(iso_path),
        "size_bytes":   iso_path.stat().st_size,
        "distro":       distro_key,
        "distro_label": config["label"],
        "kernel":       config.get("kernel"),
        "initrd":       config.get("initrd"),
        "cmdline":      config.get("cmdline"),
    }
