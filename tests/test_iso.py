"""
Tests for nightmare_loader.iso – ISO metadata extraction.

These tests use small mock ISO files and monkey-patch the subprocess calls
so that the tests run without requiring the genisoimage package.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nightmare_loader.iso import (
    ISOError,
    get_iso_label,
    get_iso_metadata,
    list_iso_files,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_iso(tmp_path) -> Path:
    """Create a small dummy file that acts as a fake ISO."""
    iso = tmp_path / "test.iso"
    iso.write_bytes(b"\x00" * 2048)
    return iso


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

    def test_falls_back_to_empty_when_isoinfo_unavailable(self, fake_iso):
        """When isoinfo is missing and the file isn't a zip, return []."""
        with patch("nightmare_loader.iso._isoinfo_available", return_value=False):
            files = list_iso_files(fake_iso)
        assert files == []

    def test_isoinfo_failure_falls_back_gracefully(self, fake_iso):
        """If isoinfo returns non-zero, fall back without raising."""
        bad_result = MagicMock()
        bad_result.returncode = 1
        bad_result.stdout = ""
        with patch("nightmare_loader.iso._isoinfo_available", return_value=True), \
             patch("subprocess.run", return_value=bad_result):
            files = list_iso_files(fake_iso)
        # Fallback to zip attempt then empty list – should not raise
        assert isinstance(files, list)


# ---------------------------------------------------------------------------
# get_iso_label
# ---------------------------------------------------------------------------

class TestGetIsoLabel:
    def test_returns_volume_label_from_isoinfo(self, fake_iso):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "CD-ROM is in ISO 9660 format\n"
            "System id: \n"
            "Volume id: Ubuntu 22.04 LTS amd64\n"
            "Volume set id: \n"
        )
        with patch("nightmare_loader.iso._isoinfo_available", return_value=True), \
             patch("subprocess.run", return_value=mock_result):
            label = get_iso_label(fake_iso)

        assert label == "Ubuntu 22.04 LTS amd64"

    def test_falls_back_to_filename_stem(self, fake_iso):
        with patch("nightmare_loader.iso._isoinfo_available", return_value=False):
            label = get_iso_label(fake_iso)
        assert label == fake_iso.stem


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
