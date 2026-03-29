"""
Tests for nightmare_loader.launcher – desktop launcher installation helpers.
"""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

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
