"""
Tests for nightmare_loader.drive – drive utility helpers that do not require
real block devices.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from nightmare_loader.drive import (
    DriveError,
    _partition_name,
    _check_not_mounted,
)


class TestPartitionName:
    """Unit tests for the partition naming helper."""

    def test_sdb_gives_sdb1(self):
        assert _partition_name("/dev/sdb", 1) == "/dev/sdb1"

    def test_sdb_partition_2(self):
        assert _partition_name("/dev/sdb", 2) == "/dev/sdb2"

    def test_nvme_device_uses_p_separator(self):
        assert _partition_name("/dev/nvme0n1", 1) == "/dev/nvme0n1p1"

    def test_mmcblk_uses_p_separator(self):
        assert _partition_name("/dev/mmcblk0", 1) == "/dev/mmcblk0p1"

    def test_sda_partition_3(self):
        assert _partition_name("/dev/sda", 3) == "/dev/sda3"


class TestCheckNotMounted:
    """Unit tests for _check_not_mounted."""

    def test_raises_if_mounted(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/dev/sdb1 /mnt/usb vfat rw,relatime 0 0\n"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(DriveError, match="mounted"):
                _check_not_mounted("/dev/sdb")

    def test_passes_if_not_mounted(self):
        mock_result = MagicMock()
        mock_result.returncode = 1  # grep returns 1 when no match
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            # Should not raise
            _check_not_mounted("/dev/sdb")


class TestListRemovableDrives:
    """Tests for list_removable_drives with mocked lsblk output."""

    def test_returns_usb_drives(self):
        from nightmare_loader.drive import list_removable_drives

        lsblk_output = {
            "blockdevices": [
                {
                    "name": "sda",
                    "size": "500107862016",
                    "model": "Samsung SSD",
                    "tran": "sata",
                    "type": "disk",
                    "hotplug": False,
                },
                {
                    "name": "sdb",
                    "size": "16013852672",
                    "model": "SanDisk Ultra",
                    "tran": "usb",
                    "type": "disk",
                    "hotplug": True,
                },
            ]
        }
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(lsblk_output)

        with patch("subprocess.run", return_value=mock_result):
            drives = list_removable_drives()

        assert len(drives) == 1
        assert drives[0]["device"] == "/dev/sdb"
        assert drives[0]["model"] == "SanDisk Ultra"
        assert drives[0]["transport"] == "usb"

    def test_raises_on_lsblk_failure(self):
        from nightmare_loader.drive import list_removable_drives

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "lsblk: error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(DriveError):
                list_removable_drives()

    def test_empty_when_no_removable_devices(self):
        from nightmare_loader.drive import list_removable_drives

        lsblk_output = {
            "blockdevices": [
                {
                    "name": "sda",
                    "size": "500107862016",
                    "model": "HDD",
                    "tran": "sata",
                    "type": "disk",
                    "hotplug": False,
                }
            ]
        }
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(lsblk_output)

        with patch("subprocess.run", return_value=mock_result):
            drives = list_removable_drives()

        assert drives == []
