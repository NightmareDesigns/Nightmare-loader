"""
Tests for nightmare_loader.launcher – desktop launcher installation helpers.
"""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nightmare_loader.launcher import install_desktop_launcher


class TestInstallDesktopLauncher:
    def test_creates_applications_dir(self, tmp_path):
        apps_dir = tmp_path / ".local" / "share" / "applications"
        with patch("nightmare_loader.launcher._XDG_APPS_DIR", apps_dir):
            install_desktop_launcher()
        assert apps_dir.is_dir()

    def test_writes_desktop_file(self, tmp_path):
        apps_dir = tmp_path / ".local" / "share" / "applications"
        with patch("nightmare_loader.launcher._XDG_APPS_DIR", apps_dir):
            paths = install_desktop_launcher()
        assert len(paths) >= 1
        assert paths[0].name == "nightmare-loader.desktop"
        assert paths[0].exists()

    def test_desktop_file_contains_app_name(self, tmp_path):
        apps_dir = tmp_path / ".local" / "share" / "applications"
        with patch("nightmare_loader.launcher._XDG_APPS_DIR", apps_dir):
            paths = install_desktop_launcher()
        content = paths[0].read_text()
        assert "Nightmare Loader" in content

    def test_exec_uses_provided_executable(self, tmp_path):
        apps_dir = tmp_path / ".local" / "share" / "applications"
        with patch("nightmare_loader.launcher._XDG_APPS_DIR", apps_dir):
            paths = install_desktop_launcher(executable="/usr/local/bin/nightmare-loader-gui")
        content = paths[0].read_text()
        assert "Exec=/usr/local/bin/nightmare-loader-gui" in content

    def test_install_to_desktop_creates_second_file(self, tmp_path):
        apps_dir = tmp_path / "applications"
        desktop_dir = tmp_path / "Desktop"
        desktop_dir.mkdir()
        with (
            patch("nightmare_loader.launcher._XDG_APPS_DIR", apps_dir),
            patch("nightmare_loader.launcher._DESKTOP_DIR", desktop_dir),
        ):
            paths = install_desktop_launcher(install_to_desktop=True)
        assert len(paths) == 2
        assert any(p.parent == desktop_dir for p in paths)

    def test_desktop_shortcut_is_executable(self, tmp_path):
        apps_dir = tmp_path / "applications"
        desktop_dir = tmp_path / "Desktop"
        desktop_dir.mkdir()
        with (
            patch("nightmare_loader.launcher._XDG_APPS_DIR", apps_dir),
            patch("nightmare_loader.launcher._DESKTOP_DIR", desktop_dir),
        ):
            paths = install_desktop_launcher(install_to_desktop=True)
        desktop_file = next(p for p in paths if p.parent == desktop_dir)
        assert desktop_file.stat().st_mode & stat.S_IXUSR

    def test_no_desktop_shortcut_when_flag_false(self, tmp_path):
        apps_dir = tmp_path / "applications"
        desktop_dir = tmp_path / "Desktop"
        desktop_dir.mkdir()
        with (
            patch("nightmare_loader.launcher._XDG_APPS_DIR", apps_dir),
            patch("nightmare_loader.launcher._DESKTOP_DIR", desktop_dir),
        ):
            paths = install_desktop_launcher(install_to_desktop=False)
        assert len(paths) == 1
        assert paths[0].parent == apps_dir


class TestInstallWindowsShortcut:
    """Tests for the Windows .lnk shortcut creation path."""

    def test_dispatches_to_windows_on_win32(self, tmp_path):
        from nightmare_loader import launcher as lnch

        with patch("nightmare_loader.launcher.sys") as mock_sys, \
             patch.object(lnch, "_install_windows_shortcut", return_value=[]) as mock_win, \
             patch.object(lnch, "_install_linux_desktop", return_value=[]) as mock_lin:
            mock_sys.platform = "win32"
            install_desktop_launcher()
            mock_win.assert_called_once()
            mock_lin.assert_not_called()

    def test_dispatches_to_linux_on_linux(self, tmp_path):
        from nightmare_loader import launcher as lnch
        apps_dir = tmp_path / "applications"

        with patch("nightmare_loader.launcher.sys") as mock_sys, \
             patch.object(lnch, "_install_windows_shortcut", return_value=[]) as mock_win, \
             patch.object(lnch, "_install_linux_desktop", return_value=[]) as mock_lin:
            mock_sys.platform = "linux"
            install_desktop_launcher()
            mock_lin.assert_called_once()
            mock_win.assert_not_called()

    def test_create_lnk_calls_powershell(self, tmp_path):
        from nightmare_loader.launcher import _create_lnk
        dest = tmp_path / "NL.lnk"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _create_lnk(dest, "C:\\some\\exe.exe", "description")
        # PowerShell should have been called with WScript.Shell in the command
        cmd_args = mock_run.call_args[0][0]
        assert cmd_args[0] == "powershell"
        # The PS script is the last argument (after "-NoProfile" and "-Command")
        ps_cmd = cmd_args[-1]
        assert "WScript.Shell" in ps_cmd

    def test_create_lnk_raises_on_failure(self, tmp_path):
        from nightmare_loader.launcher import _create_lnk
        dest = tmp_path / "NL.lnk"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Access denied"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(OSError, match="Failed to create shortcut"):
                _create_lnk(dest, "C:\\exe.exe", "desc")

    def test_install_windows_shortcut_menu_only(self, tmp_path):
        from nightmare_loader.launcher import _install_windows_shortcut
        start_menu = tmp_path / "StartMenu"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with patch("nightmare_loader.launcher._windows_start_menu_dir", return_value=start_menu), \
             patch("subprocess.run", return_value=mock_result):
            paths = _install_windows_shortcut(
                install_to_desktop=False,
                executable="C:\\nightmare-loader-gui.exe",
            )
        assert len(paths) == 1
        assert paths[0] == start_menu / "Nightmare Loader.lnk"

    def test_install_windows_shortcut_with_desktop(self, tmp_path):
        from nightmare_loader.launcher import _install_windows_shortcut
        start_menu = tmp_path / "StartMenu"
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with patch("nightmare_loader.launcher._windows_start_menu_dir", return_value=start_menu), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("subprocess.run", return_value=mock_result):
            paths = _install_windows_shortcut(
                install_to_desktop=True,
                executable="C:\\nightmare-loader-gui.exe",
            )
        assert len(paths) == 2
