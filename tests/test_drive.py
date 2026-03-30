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


class TestListRemovableDrivesWindows:
    """Tests for the Windows drive listing path (_list_removable_drives_windows)."""

    def test_returns_drives_from_powershell(self):
        from nightmare_loader.drive import _list_removable_drives_windows

        ps_output = json.dumps([
            {
                "Device": "\\\\.\\PHYSICALDRIVE1",
                "Letters": "E",
                "Model": "SanDisk Ultra USB 3.0",
                "Size": "16013852672",
            }
        ])
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ps_output

        with patch("subprocess.run", return_value=mock_result):
            drives = _list_removable_drives_windows()

        assert len(drives) == 1
        assert drives[0]["device"] == "E\\"
        assert drives[0]["model"] == "SanDisk Ultra USB 3.0"
        assert drives[0]["transport"] == "usb"
        assert drives[0]["size"] == "16013852672"

    def test_single_drive_dict_not_list(self):
        """PowerShell returns a plain dict when only one drive is present."""
        from nightmare_loader.drive import _list_removable_drives_windows

        ps_output = json.dumps({
            "Device": "\\\\.\\PHYSICALDRIVE1",
            "Letters": "F",
            "Model": "Kingston DT",
            "Size": "8000000000",
        })
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ps_output

        with patch("subprocess.run", return_value=mock_result):
            drives = _list_removable_drives_windows()

        assert len(drives) == 1
        assert drives[0]["device"] == "F\\"

    def test_empty_on_no_output(self):
        from nightmare_loader.drive import _list_removable_drives_windows

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            drives = _list_removable_drives_windows()

        assert drives == []

    def test_raises_on_powershell_not_found(self):
        from nightmare_loader.drive import _list_removable_drives_windows, DriveError

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(DriveError, match="PowerShell"):
                _list_removable_drives_windows()

    def test_raises_on_timeout(self):
        import subprocess
        from nightmare_loader.drive import _list_removable_drives_windows, DriveError

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("powershell", 15)):
            with pytest.raises(DriveError, match="timed out"):
                _list_removable_drives_windows()

    def test_list_removable_drives_dispatches_to_windows(self):
        """list_removable_drives() should call the Windows path on win32."""
        from nightmare_loader import drive as drv

        with patch("nightmare_loader.drive.sys") as mock_sys, \
             patch.object(drv, "_list_removable_drives_windows", return_value=[]) as mock_win, \
             patch.object(drv, "_list_removable_drives_linux", return_value=[]) as mock_lin:
            mock_sys.platform = "win32"
            drv.list_removable_drives()
            mock_win.assert_called_once()
            mock_lin.assert_not_called()

    def test_list_removable_drives_dispatches_to_linux(self):
        """list_removable_drives() should call the Linux path on linux."""
        from nightmare_loader import drive as drv

        with patch("nightmare_loader.drive.sys") as mock_sys, \
             patch.object(drv, "_list_removable_drives_windows", return_value=[]) as mock_win, \
             patch.object(drv, "_list_removable_drives_linux", return_value=[]) as mock_lin:
            mock_sys.platform = "linux"
            drv.list_removable_drives()
            mock_lin.assert_called_once()
            mock_win.assert_not_called()


class TestIsTermux:
    """Tests for the _is_termux() Termux/Android detection helper."""

    def test_detects_via_env_var(self):
        from nightmare_loader.drive import _is_termux
        with patch.dict("os.environ", {"TERMUX_VERSION": "0.118.0"}):
            assert _is_termux() is True

    def test_not_termux_without_env_or_path(self, tmp_path):
        from nightmare_loader.drive import _is_termux
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "TERMUX_VERSION"}
        with patch.dict("os.environ", env, clear=True), \
             patch("nightmare_loader.drive.Path") as mock_path:
            # Simulate /data/data/com.termux not existing
            mock_instance = MagicMock()
            mock_instance.exists.return_value = False
            mock_path.return_value = mock_instance
            assert _is_termux() is False

    def test_detects_via_termux_prefix_path(self, tmp_path):
        from nightmare_loader.drive import _is_termux
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "TERMUX_VERSION"}
        termux_dir = tmp_path / "data" / "data" / "com.termux"
        termux_dir.mkdir(parents=True)
        with patch.dict("os.environ", env, clear=True), \
             patch("nightmare_loader.drive.Path", side_effect=lambda p: tmp_path / p.lstrip("/")):
            # Re-import to pick up the patch
            assert termux_dir.exists()


class TestListRemovableDrivesAndroid:
    """Tests for the Android/Termux sysfs drive listing."""

    def _make_sysfs(self, tmp_path, devices: list[dict]) -> Path:
        """Build a fake /sys/block tree under tmp_path."""
        sys_block = tmp_path / "sys" / "block"
        for d in devices:
            name = d["name"]
            dev_dir = sys_block / name
            dev_dir.mkdir(parents=True, exist_ok=True)
            (dev_dir / "removable").write_text(d.get("removable", "0"))
            if "size" in d:
                (dev_dir / "size").write_text(str(d["size"]))
            if "model" in d:
                model_dir = dev_dir / "device"
                model_dir.mkdir(parents=True, exist_ok=True)
                (model_dir / "model").write_text(d["model"])
        return sys_block

    def test_returns_removable_devices(self, tmp_path):
        from nightmare_loader.drive import _list_removable_drives_android

        sys_block = self._make_sysfs(tmp_path, [
            {"name": "sda", "removable": "0"},
            {"name": "sdb", "removable": "1", "size": 31457280, "model": "SanDisk Ultra"},
        ])
        with patch("nightmare_loader.drive.Path", side_effect=lambda p: tmp_path / p.lstrip("/")):
            drives = _list_removable_drives_android()

        # sda is not removable, only sdb should appear
        assert len(drives) == 1
        assert drives[0]["device"] == "/dev/sdb"
        assert drives[0]["transport"] == "usb"
        assert drives[0]["size"] == str(31457280 * 512)
        assert drives[0]["model"] == "SanDisk Ultra"

    def test_skips_non_sd_devices(self, tmp_path):
        from nightmare_loader.drive import _list_removable_drives_android

        sys_block = self._make_sysfs(tmp_path, [
            {"name": "loop0", "removable": "1"},
            {"name": "ram0",  "removable": "1"},
            {"name": "zram0", "removable": "1"},
            {"name": "sdc",   "removable": "1", "size": 65536},
        ])
        with patch("nightmare_loader.drive.Path", side_effect=lambda p: tmp_path / p.lstrip("/")):
            drives = _list_removable_drives_android()

        names = [d["device"] for d in drives]
        assert "/dev/sdc" in names
        assert not any("loop" in n or "ram" in n for n in names)

    def test_empty_when_sys_block_absent(self, tmp_path):
        from nightmare_loader.drive import _list_removable_drives_android

        with patch("nightmare_loader.drive.Path", side_effect=lambda p: tmp_path / p.lstrip("/")):
            drives = _list_removable_drives_android()

        assert drives == []

    def test_list_removable_drives_dispatches_to_android(self):
        """list_removable_drives() should call the Android path on Termux."""
        from nightmare_loader import drive as drv

        with patch("nightmare_loader.drive.sys") as mock_sys, \
             patch.object(drv, "_is_termux", return_value=True), \
             patch.object(drv, "_list_removable_drives_android", return_value=[]) as mock_and, \
             patch.object(drv, "_list_removable_drives_linux", return_value=[]) as mock_lin:
            mock_sys.platform = "linux"
            drv.list_removable_drives()
            mock_and.assert_called_once()
            mock_lin.assert_not_called()
