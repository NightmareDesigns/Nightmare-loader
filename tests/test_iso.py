"""
Tests for nightmare_loader.iso – ISO metadata extraction.

These tests use small mock ISO files and monkey-patch the subprocess calls
so that the tests run without requiring the genisoimage package.
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nightmare_loader.iso import (
    ISOError,
    _7z_cmd,
    _pvd_label,
    _read_pvd,
    get_iso_label,
    get_iso_metadata,
    list_iso_files,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CD001 = b"CD001"
_ISO_SECTOR = 2048
_PVD_SECTOR = 16


def _make_iso_pvd(label: str = "TESTISO") -> bytes:
    """Return a minimal 2048-byte Primary Volume Descriptor."""
    pvd = bytearray(_ISO_SECTOR)
    pvd[0]   = 1           # Type: Primary Volume Descriptor
    pvd[1:6] = _CD001
    pvd[6]   = 1           # Version
    label_bytes = label.encode("ascii").ljust(32)[:32]
    pvd[40:72] = label_bytes
    return bytes(pvd)


@pytest.fixture()
def fake_iso(tmp_path) -> Path:
    """Create a minimal valid ISO 9660 file (sectors 0-16 filled)."""
    iso = tmp_path / "test.iso"
    # Write 17 sectors: sectors 0-15 are zeroed system area, sector 16 is PVD
    data = bytearray(17 * _ISO_SECTOR)
    pvd = _make_iso_pvd("TESTISO")
    data[16 * _ISO_SECTOR : 17 * _ISO_SECTOR] = pvd
    iso.write_bytes(bytes(data))
    return iso


@pytest.fixture()
def tiny_iso(tmp_path) -> Path:
    """A small file that is NOT a valid ISO (used for error-path tests)."""
    iso = tmp_path / "tiny.iso"
    iso.write_bytes(b"\x00" * 2048)
    return iso


# ---------------------------------------------------------------------------
# _read_pvd / _pvd_label
# ---------------------------------------------------------------------------

class TestReadPvd:
    def test_reads_valid_pvd(self, fake_iso):
        pvd = _read_pvd(fake_iso)
        assert pvd[1:6] == _CD001

    def test_raises_for_missing_file(self):
        with pytest.raises(ISOError, match="Cannot read"):
            _read_pvd(Path("/nonexistent/image.iso"))

    def test_raises_for_invalid_signature(self, tiny_iso):
        with pytest.raises(ISOError, match="CD001|too small"):
            _read_pvd(tiny_iso)


class TestPvdLabel:
    def test_extracts_label(self):
        pvd = _make_iso_pvd("Ubuntu 24.04 LTS")
        assert _pvd_label(pvd) == "Ubuntu 24.04 LTS"

    def test_strips_padding(self):
        pvd = _make_iso_pvd("KALI")
        assert _pvd_label(pvd) == "KALI"

    def test_empty_label_returns_empty_string(self):
        pvd = _make_iso_pvd("")
        assert _pvd_label(pvd) == ""


# ---------------------------------------------------------------------------
# list_iso_files
# ---------------------------------------------------------------------------

class TestListIsoFiles:
    def test_raises_for_missing_file(self):
        with pytest.raises(ISOError, match="not found"):
            list_iso_files("/nonexistent/path/file.iso")

    def test_uses_isoinfo_when_available(self, fake_iso):
        """When isoinfo is available and returns data, use that data."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "/casper/vmlinuz;1\n"
            "/casper/initrd;1\n"
            "/.disk/info;1\n"
        )
        with patch("nightmare_loader.iso._isoinfo_available", return_value=True), \
             patch("subprocess.run", return_value=mock_result):
            files = list_iso_files(fake_iso)

        assert "casper/vmlinuz" in files
        assert "casper/initrd" in files

    def test_falls_back_to_7z_when_isoinfo_unavailable(self, fake_iso):
        """When isoinfo is absent but 7z is present, use 7z output."""
        z7_output = (
            "Path = casper/vmlinuz\n"
            "Size = 12345\n"
            "Path = casper/initrd\n"
            "Size = 67890\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = z7_output

        with patch("nightmare_loader.iso._isoinfo_available", return_value=False), \
             patch("nightmare_loader.iso._7z_cmd", return_value="7z"), \
             patch("subprocess.run", return_value=mock_result):
            files = list_iso_files(fake_iso)

        assert "casper/vmlinuz" in files
        assert "casper/initrd" in files

    def test_falls_back_to_empty_when_all_backends_fail(self, fake_iso):
        """When all backends fail, return [] without raising."""
        bad = MagicMock()
        bad.returncode = 1
        bad.stdout = ""
        with patch("nightmare_loader.iso._isoinfo_available", return_value=False), \
             patch("nightmare_loader.iso._7z_cmd", return_value=None):
            files = list_iso_files(fake_iso)
        assert files == []

    def test_isoinfo_failure_falls_back_to_7z(self, fake_iso):
        """If isoinfo returns non-zero, fall back to 7z."""
        bad = MagicMock(returncode=1, stdout="")
        good = MagicMock(returncode=0, stdout="Path = live/vmlinuz\n")

        call_count = [0]

        def mock_run(cmd, **kw):
            call_count[0] += 1
            if "isoinfo" in cmd:
                return bad
            return good

        with patch("nightmare_loader.iso._isoinfo_available", return_value=True), \
             patch("nightmare_loader.iso._7z_cmd", return_value="7z"), \
             patch("subprocess.run", side_effect=mock_run):
            files = list_iso_files(fake_iso)

        assert "live/vmlinuz" in files

    def test_7z_strips_leading_slashes(self, fake_iso):
        """Paths from 7z should have leading slashes stripped."""
        mock_result = MagicMock(returncode=0,
                                stdout="Path = /arch/boot/x86_64/vmlinuz-linux\n")
        with patch("nightmare_loader.iso._isoinfo_available", return_value=False), \
             patch("nightmare_loader.iso._7z_cmd", return_value="7z"), \
             patch("subprocess.run", return_value=mock_result):
            files = list_iso_files(fake_iso)
        assert "arch/boot/x86_64/vmlinuz-linux" in files


# ---------------------------------------------------------------------------
# get_iso_label
# ---------------------------------------------------------------------------

class TestGetIsoLabel:
    def test_reads_label_from_pvd_without_external_tools(self, fake_iso):
        """Pure-Python PVD reader must work without isoinfo."""
        with patch("nightmare_loader.iso._isoinfo_available", return_value=False), \
             patch("nightmare_loader.iso.shutil.which", return_value=None):
            label = get_iso_label(fake_iso)
        assert label == "TESTISO"

    def test_returns_volume_label_from_isoinfo(self, tiny_iso):
        """When PVD read fails, isoinfo is the fallback."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "CD-ROM is in ISO 9660 format\n"
            "Volume id: Ubuntu 22.04 LTS amd64\n"
        )
        with patch("nightmare_loader.iso._isoinfo_available", return_value=True), \
             patch("nightmare_loader.iso.shutil.which", return_value=None), \
             patch("subprocess.run", return_value=mock_result):
            label = get_iso_label(tiny_iso)

        assert label == "Ubuntu 22.04 LTS amd64"

    def test_falls_back_to_filename_stem(self, tiny_iso):
        """When everything fails, use the filename stem."""
        with patch("nightmare_loader.iso._isoinfo_available", return_value=False), \
             patch("nightmare_loader.iso.shutil.which", return_value=None):
            label = get_iso_label(tiny_iso)
        assert label == tiny_iso.stem

    def test_pvd_label_takes_priority_over_isoinfo(self, fake_iso):
        """PVD label must be used even when isoinfo is available."""
        isoinfo_result = MagicMock(returncode=0,
                                   stdout="Volume id: WRONG_LABEL\n")
        with patch("nightmare_loader.iso._isoinfo_available", return_value=True), \
             patch("nightmare_loader.iso.shutil.which", return_value=None), \
             patch("subprocess.run", return_value=isoinfo_result):
            label = get_iso_label(fake_iso)
        # The PVD reader runs before isoinfo, so it should win
        assert label == "TESTISO"


# ---------------------------------------------------------------------------
# get_iso_metadata
# ---------------------------------------------------------------------------

class TestGetIsoMetadata:
    def test_returns_dict_with_required_keys(self, fake_iso):
        with patch("nightmare_loader.iso.list_iso_files", return_value=[]), \
             patch("nightmare_loader.iso.get_iso_label", return_value="TESTISO"):
            meta = get_iso_metadata(fake_iso)

        required = {"path", "filename", "label", "size_bytes", "distro",
                    "distro_label", "kernel", "initrd", "cmdline"}
        assert required.issubset(meta.keys())

    def test_ubuntu_iso_detected_correctly(self, fake_iso):
        ubuntu_files = ["casper/vmlinuz", "casper/initrd", ".disk/info"]
        with patch("nightmare_loader.iso.list_iso_files", return_value=ubuntu_files), \
             patch("nightmare_loader.iso.get_iso_label", return_value="Ubuntu 22.04"):
            meta = get_iso_metadata(fake_iso)

        assert meta["distro"] == "ubuntu"
        assert meta["distro_label"] == "Ubuntu"
        assert meta["kernel"] == "/casper/vmlinuz"
        assert meta["initrd"] == "/casper/initrd"

    def test_filename_and_path_correct(self, fake_iso):
        with patch("nightmare_loader.iso.list_iso_files", return_value=[]), \
             patch("nightmare_loader.iso.get_iso_label", return_value="TEST"):
            meta = get_iso_metadata(fake_iso)

        assert meta["filename"] == fake_iso.name
        assert str(fake_iso.resolve()) == meta["path"]

    def test_size_bytes_populated(self, fake_iso):
        with patch("nightmare_loader.iso.list_iso_files", return_value=[]), \
             patch("nightmare_loader.iso.get_iso_label", return_value="T"):
            meta = get_iso_metadata(fake_iso)
        assert meta["size_bytes"] == fake_iso.stat().st_size

    def test_raises_for_nonexistent_iso(self):
        with pytest.raises(ISOError):
            get_iso_metadata("/nonexistent/path/to.iso")
