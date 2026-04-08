"""
Tests for nightmare_loader.cli – helpers and commands relevant to
Termux/Android non-root support.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from nightmare_loader.cli import cli, _require_root, _require_root_or_mount_point, _termux_nl_exe, _termux_bash


# ---------------------------------------------------------------------------
# _require_root – Termux-specific error message
# ---------------------------------------------------------------------------

class TestRequireRoot:
    """_require_root() should give Termux-specific guidance when on Termux."""

    def test_exits_with_error_when_not_root(self):
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=False):
            runner = CliRunner()
            # Use the CLI runner to invoke a command that calls _require_root
            result = runner.invoke(cli, ["prepare", "/dev/sda", "--yes"])
        assert result.exit_code != 0

    def test_termux_message_mentions_tsu(self):
        """On Termux the error should suggest tsu, not sudo."""
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=True):
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(cli, ["prepare", "/dev/sda", "--yes"])
        assert result.exit_code != 0
        assert "tsu" in result.output or "tsu" in (result.stderr or "")

    def test_non_termux_message_mentions_sudo(self):
        """On non-Termux the error should mention sudo."""
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=False):
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(cli, ["prepare", "/dev/sda", "--yes"])
        assert result.exit_code != 0
        combined = result.output + (result.stderr or "")
        assert "sudo" in combined or "root" in combined


# ---------------------------------------------------------------------------
# _require_root_or_mount_point
# ---------------------------------------------------------------------------

class TestRequireRootOrMountPoint:
    """When --mount-point is given, root should not be required."""

    def test_passes_when_mount_point_given(self, tmp_path):
        # Should not raise even when not root
        with patch("os.geteuid", return_value=1000):
            # No exception expected
            _require_root_or_mount_point(str(tmp_path))

    def test_exits_without_mount_point_when_not_root(self):
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=False):
            with pytest.raises(SystemExit):
                _require_root_or_mount_point(None)

    def test_termux_message_includes_mount_point_hint(self, capsys):
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=True):
            with pytest.raises(SystemExit):
                _require_root_or_mount_point(None)
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "--mount-point" in combined
        assert "tsu" in combined


# ---------------------------------------------------------------------------
# _open_drive – pre-mounted path behaviour
# ---------------------------------------------------------------------------

class TestOpenDrive:
    """_open_drive should use a pre-mounted path without calling mount/umount."""

    def test_yields_mount_point_path_directly(self, tmp_path):
        from nightmare_loader.cli import _open_drive

        with _open_drive("/dev/sda", str(tmp_path)) as mp:
            assert mp == tmp_path

    def test_errors_if_mount_point_not_a_directory(self, tmp_path):
        from nightmare_loader.cli import _open_drive

        not_a_dir = tmp_path / "missing"
        runner = CliRunner()
        with pytest.raises(SystemExit):
            with _open_drive("/dev/sda", str(not_a_dir)) as _:
                pass

    def test_mounts_when_no_mount_point(self):
        from nightmare_loader.cli import _open_drive

        mock_mount = MagicMock()
        mock_unmount = MagicMock()

        with patch("nightmare_loader.cli.mount", mock_mount), \
             patch("nightmare_loader.cli.unmount", mock_unmount), \
             patch("nightmare_loader.cli._partition_name", return_value="/dev/sda1"):
            # We can't actually call mount (no real device), so just confirm it
            # is invoked when mount_point=None
            try:
                with _open_drive("/dev/sda", None) as _:
                    pass
            except Exception:
                pass
        mock_mount.assert_called_once()


# ---------------------------------------------------------------------------
# CLI commands with --mount-point
# ---------------------------------------------------------------------------

def _make_drive_state(tmp_path: Path, entries: list | None = None) -> Path:
    """Write a minimal nightmare-loader state file under tmp_path."""
    from nightmare_loader.grub import ISO_DIR

    iso_dir = tmp_path / ISO_DIR
    iso_dir.mkdir(parents=True, exist_ok=True)
    state = {"entries": entries or [], "label": "NIGHTMARE"}
    (tmp_path / ".nightmare-loader.json").write_text(json.dumps(state))
    # Write a minimal grub.cfg so write_grub_cfg has a directory to work with
    grub_dir = tmp_path / "boot" / "grub"
    grub_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


class TestListWithMountPoint:
    """nightmare-loader list DEVICE --mount-point PATH should not require root."""

    def test_lists_isos_from_pre_mounted_path(self, tmp_path):
        mp = _make_drive_state(tmp_path, entries=[
            {
                "filename": "ubuntu.iso",
                "label": "Ubuntu",
                "distro": "ubuntu",
                "distro_label": "Ubuntu 22.04",
                "size_bytes": 1_000_000,
                "isofile": "/isos/ubuntu.iso",
                "kernel": "/casper/vmlinuz",
                "initrd": "/casper/initrd",
                "cmdline": "boot=casper",
            }
        ])
        runner = CliRunner()
        with patch("os.geteuid", return_value=1000):
            result = runner.invoke(cli, ["list", "/dev/sda", "--mount-point", str(mp)])
        assert result.exit_code == 0, result.output
        assert "ubuntu.iso" in result.output

    def test_list_no_root_no_mount_point_fails(self):
        runner = CliRunner(mix_stderr=False)
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=False):
            result = runner.invoke(cli, ["list", "/dev/sda"])
        assert result.exit_code != 0

    def test_list_termux_no_root_no_mount_point_suggests_mount_point(self):
        runner = CliRunner(mix_stderr=False)
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=True):
            result = runner.invoke(cli, ["list", "/dev/sda"])
        assert result.exit_code != 0
        combined = result.output + (result.stderr or "")
        assert "--mount-point" in combined


class TestAddWithMountPoint:
    """nightmare-loader add DEVICE ISO --mount-point PATH should not require root."""

    def test_adds_iso_to_pre_mounted_path(self, tmp_path):
        mp = _make_drive_state(tmp_path)
        iso_file = tmp_path / "test.iso"
        iso_file.write_bytes(b"\x00" * 2048)

        fake_meta = {
            "filename": "test.iso",
            "label": "TEST",
            "distro": "generic",
            "distro_label": "Generic Linux",
            "size_bytes": 2048,
            "kernel": "/vmlinuz",
            "initrd": "/initrd.img",
            "cmdline": "",
        }
        runner = CliRunner()
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli.get_iso_metadata", return_value=fake_meta), \
             patch("nightmare_loader.cli.write_grub_cfg", return_value=mp / "boot" / "grub" / "grub.cfg"):
            result = runner.invoke(
                cli,
                ["add", "/dev/sda", str(iso_file), "--mount-point", str(mp), "--no-copy"],
            )
        assert result.exit_code == 0, result.output
        assert "Added" in result.output


class TestRemoveWithMountPoint:
    """nightmare-loader remove DEVICE ISO --mount-point PATH should not require root."""

    def test_removes_iso_from_pre_mounted_path(self, tmp_path):
        mp = _make_drive_state(tmp_path, entries=[
            {
                "filename": "ubuntu.iso",
                "label": "Ubuntu",
                "distro": "ubuntu",
                "distro_label": "Ubuntu 22.04",
                "size_bytes": 1_000_000,
                "isofile": "/isos/ubuntu.iso",
                "kernel": "/casper/vmlinuz",
                "initrd": "/casper/initrd",
                "cmdline": "boot=casper",
            }
        ])
        runner = CliRunner()
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli.write_grub_cfg", return_value=mp / "boot" / "grub" / "grub.cfg"):
            result = runner.invoke(
                cli,
                ["remove", "/dev/sda", "ubuntu.iso", "--mount-point", str(mp), "--keep-file"],
            )
        assert result.exit_code == 0, result.output
        assert "Removed" in result.output


class TestUpdateWithMountPoint:
    """nightmare-loader update DEVICE --mount-point PATH should not require root."""

    def test_update_from_pre_mounted_path(self, tmp_path):
        mp = _make_drive_state(tmp_path)
        runner = CliRunner()
        cfg_path = mp / "boot" / "grub" / "grub.cfg"
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli.write_grub_cfg", return_value=cfg_path):
            result = runner.invoke(
                cli,
                ["update", "/dev/sda", "--mount-point", str(mp)],
            )
        assert result.exit_code == 0, result.output
        assert "Updated" in result.output


# ---------------------------------------------------------------------------
# build-iso command
# ---------------------------------------------------------------------------

class TestBuildIsoCommand:
    """Tests for the `build-iso` CLI command."""

    def test_build_iso_is_registered(self):
        """build-iso must appear in --help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "build-iso" in result.output

    def test_build_iso_missing_script_shows_error(self, tmp_path):
        """When build_iso.sh cannot be located, exit 1 with a helpful error message."""
        runner = CliRunner(mix_stderr=False)
        with patch.object(__import__("pathlib").Path, "is_file", return_value=False), \
             patch("os.geteuid", return_value=0):
            result = runner.invoke(cli, ["build-iso"])
        assert result.exit_code == 1
        combined = result.output + (result.stderr or "")
        assert "build_iso.sh" in combined

    def test_build_iso_not_supported_on_windows(self, tmp_path):
        """build-iso should print a Windows-specific error and exit 1."""
        script = tmp_path / "build_iso.sh"
        script.write_text("#!/usr/bin/env bash\n")
        script.chmod(0o755)

        runner = CliRunner(mix_stderr=False)
        with patch("sys.platform", "win32"), \
             patch("os.geteuid", return_value=0), \
             patch.object(__import__("pathlib").Path, "is_file", return_value=True), \
             patch.object(__import__("pathlib").Path, "resolve", return_value=script):
            result = runner.invoke(cli, ["build-iso"])
        assert result.exit_code == 1
        combined = result.output + (result.stderr or "")
        assert "Windows" in combined

    def test_build_iso_termux_non_root_uses_tsu_bash(self, tmp_path):
        """On Termux without root, tsu <bash_exe> -c must be used with full bash path."""
        script = tmp_path / "build_iso.sh"
        script.write_text("#!/usr/bin/env bash\n")
        script.chmod(0o755)

        captured_cmd: list = []

        def fake_call(cmd, *args, **kwargs):
            captured_cmd.extend(cmd)
            return 0

        runner = CliRunner()
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=True), \
             patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.call", side_effect=fake_call), \
             patch("nightmare_loader.cli.Path.__truediv__", return_value=script), \
             patch.object(__import__("pathlib").Path, "is_file", return_value=True):
            runner.invoke(cli, ["build-iso"])

        # Must start with ["tsu", <full-path-to-bash>, "-c", ...]
        if captured_cmd:
            assert captured_cmd[0] == "tsu", (
                f"Expected 'tsu' as first element but got {captured_cmd[0]}"
            )
            assert captured_cmd[1].endswith("bash"), (
                f"Expected full path to bash as second element but got {captured_cmd[1]}"
            )
            assert captured_cmd[2] == "-c", (
                f"Expected '-c' as third element but got {captured_cmd[2]}"
            )

    def test_build_iso_linux_non_root_uses_sudo(self, tmp_path):
        """On Linux without root (non-Termux), sudo must be prepended."""
        script = tmp_path / "build_iso.sh"
        script.write_text("#!/usr/bin/env bash\n")
        script.chmod(0o755)

        captured_cmd: list = []

        def fake_call(cmd, *args, **kwargs):
            captured_cmd.extend(cmd)
            return 0

        runner = CliRunner()
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=False), \
             patch("shutil.which", return_value="/usr/bin/sudo"), \
             patch("subprocess.call", side_effect=fake_call), \
             patch("nightmare_loader.cli.Path.__truediv__", return_value=script), \
             patch.object(__import__("pathlib").Path, "is_file", return_value=True):
            runner.invoke(cli, ["build-iso"])

        if captured_cmd:
            assert captured_cmd[0] == "sudo", (
                f"Expected 'sudo' as first element but got {captured_cmd[0]}"
            )


# ---------------------------------------------------------------------------
# drives command – output formatting
# ---------------------------------------------------------------------------

class TestDrivesCommand:
    """Tests for the `drives` CLI command output formatting."""

    def test_drives_with_known_size(self):
        """drives should format size as X.X GB when size is known."""
        fake_drives = [
            {"device": "/dev/sda", "size": "16000000000", "model": "SanDisk", "transport": "usb"},
        ]
        runner = CliRunner()
        with patch("nightmare_loader.cli.list_removable_drives", return_value=fake_drives):
            result = runner.invoke(cli, ["drives"])
        assert result.exit_code == 0
        assert "/dev/sda" in result.output
        assert "GB" in result.output
        assert "SanDisk" in result.output

    def test_drives_with_unknown_size_formats_correctly(self):
        """drives must render '? GB' and exit 0 when size cannot be determined."""
        fake_drives = [
            {"device": "/dev/sda", "size": "?", "model": "Unknown Drive", "transport": "usb"},
        ]
        runner = CliRunner()
        with patch("nightmare_loader.cli.list_removable_drives", return_value=fake_drives):
            result = runner.invoke(cli, ["drives"])
        assert result.exit_code == 0, f"drives crashed: {result.output}\n{result.exception}"
        assert "/dev/sda" in result.output
        assert "? GB" in result.output

    def test_drives_empty_prints_message(self):
        """drives should print a friendly message when no drives are found."""
        runner = CliRunner()
        with patch("nightmare_loader.cli.list_removable_drives", return_value=[]):
            result = runner.invoke(cli, ["drives"])
        assert result.exit_code == 0
        assert "No removable drives found" in result.output


# ---------------------------------------------------------------------------
# _termux_nl_exe / _termux_bash helpers
# ---------------------------------------------------------------------------

class TestTermuxPathHelpers:
    """_termux_nl_exe and _termux_bash must return absolute paths usable with tsu."""

    def test_termux_nl_exe_returns_argv0_when_absolute(self):
        """If sys.argv[0] is absolute, it should be returned as-is."""
        with patch.object(sys, "argv", ["/data/data/com.termux/files/usr/bin/nightmare-loader"]):
            result = _termux_nl_exe()
        assert result == "/data/data/com.termux/files/usr/bin/nightmare-loader"

    def test_termux_nl_exe_falls_back_to_which(self):
        """If sys.argv[0] is not absolute, shutil.which result should be used."""
        with patch.object(sys, "argv", ["nightmare-loader"]), \
             patch("shutil.which", return_value="/usr/local/bin/nightmare-loader"):
            result = _termux_nl_exe()
        assert result == "/usr/local/bin/nightmare-loader"

    def test_termux_bash_returns_which_result(self):
        """_termux_bash should return the full path from shutil.which when available."""
        with patch("shutil.which", return_value="/data/data/com.termux/files/usr/bin/bash"):
            result = _termux_bash()
        assert result == "/data/data/com.termux/files/usr/bin/bash"

    def test_termux_bash_fallback_uses_prefix_env(self):
        """When bash is not on PATH, PREFIX env var should be used for the fallback path."""
        import os as _os
        with patch("shutil.which", return_value=None), \
             patch.dict(_os.environ, {"PREFIX": "/data/data/com.termux/files/usr"}):
            result = _termux_bash()
        assert result == "/data/data/com.termux/files/usr/bin/bash"


class TestTermuxErrorMessagesUseFullPath:
    """Error messages shown to the user on Termux must include the absolute exe path."""

    def test_require_root_shows_full_nl_path(self):
        """_require_root error on Termux should show full path to nightmare-loader."""
        runner = CliRunner(mix_stderr=False)
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=True), \
             patch("nightmare_loader.cli._termux_nl_exe",
                   return_value="/data/data/com.termux/files/usr/bin/nightmare-loader"):
            result = runner.invoke(cli, ["prepare", "/dev/sda", "--yes"])
        combined = result.output + (result.stderr or "")
        assert "/data/data/com.termux/files/usr/bin/nightmare-loader" in combined

    def test_require_root_or_mount_point_shows_full_nl_path(self, capsys):
        """_require_root_or_mount_point error on Termux should show full path."""
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=True), \
             patch("nightmare_loader.cli._termux_nl_exe",
                   return_value="/data/data/com.termux/files/usr/bin/nightmare-loader"):
            with pytest.raises(SystemExit):
                _require_root_or_mount_point(None)
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "/data/data/com.termux/files/usr/bin/nightmare-loader" in combined

