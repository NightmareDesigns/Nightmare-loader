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

from nightmare_loader.cli import cli, _require_root, _require_root_or_mount_point


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
            runner = CliRunner()
            result = runner.invoke(cli, ["prepare", "/dev/sda", "--yes"])
        assert result.exit_code != 0
        assert "tsu" in result.output

    def test_non_termux_message_mentions_sudo(self):
        """On non-Termux the error should mention sudo."""
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=False):
            runner = CliRunner()
            result = runner.invoke(cli, ["prepare", "/dev/sda", "--yes"])
        assert result.exit_code != 0
        combined = result.output
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
        runner = CliRunner()
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=False):
            result = runner.invoke(cli, ["list", "/dev/sda"])
        assert result.exit_code != 0

    def test_list_termux_no_root_no_mount_point_suggests_mount_point(self):
        runner = CliRunner()
        with patch("os.geteuid", return_value=1000), \
             patch("nightmare_loader.cli._is_termux", return_value=True):
            result = runner.invoke(cli, ["list", "/dev/sda"])
        assert result.exit_code != 0
        combined = result.output
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
# nightmare-loader download
# ---------------------------------------------------------------------------

class TestDownloadList:
    """download --list should print a table of downloadable distros."""

    def test_lists_downloadable_distros(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "--list"])
        assert result.exit_code == 0, result.output
        assert "KEY" in result.output
        assert "URL" in result.output
        # at least one distro should appear
        assert "ubuntu" in result.output

    def test_list_does_not_download_anything(self, tmp_path):
        """--list must not create any files."""
        runner = CliRunner()
        with patch("urllib.request.urlretrieve") as mock_get:
            result = runner.invoke(cli, ["download", "--list", "--out", str(tmp_path)])
        assert result.exit_code == 0
        mock_get.assert_not_called()


class TestDownloadSingle:
    """download <distro> should call urlretrieve for the correct URL."""

    def _make_urlretrieve_side_effect(self):
        """Side effect that creates the destination file so rename() succeeds."""
        def _side_effect(url, dest, reporthook=None):
            Path(dest).write_bytes(b"fake iso data")
        return _side_effect

    def test_downloads_known_distro(self, tmp_path):
        runner = CliRunner()
        with patch(
            "urllib.request.urlretrieve",
            side_effect=self._make_urlretrieve_side_effect(),
        ) as mock_get:
            result = runner.invoke(
                cli, ["download", "ubuntu", "--out", str(tmp_path)]
            )
        assert result.exit_code == 0, result.output
        assert mock_get.called
        # The URL should contain 'ubuntu'
        called_url = mock_get.call_args[0][0]
        assert "ubuntu" in called_url.lower()

    def test_already_existing_file_is_skipped(self, tmp_path):
        from nightmare_loader.distros import DISTROS
        url = DISTROS["ubuntu"]["download_url"]
        filename = url.split("/")[-1]
        (tmp_path / filename).write_bytes(b"existing")

        runner = CliRunner()
        with patch("urllib.request.urlretrieve") as mock_get:
            result = runner.invoke(
                cli, ["download", "ubuntu", "--out", str(tmp_path)]
            )
        assert result.exit_code == 0
        mock_get.assert_not_called()
        assert "skipping" in result.output

    def test_unknown_distro_exits_nonzero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "nonexistent-distro-xyz"])
        assert result.exit_code != 0

    def test_download_failure_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        with patch(
            "urllib.request.urlretrieve",
            side_effect=OSError("network error"),
        ):
            result = runner.invoke(
                cli, ["download", "ubuntu", "--out", str(tmp_path)]
            )
        assert result.exit_code != 0
        combined = result.output
        assert "Failed" in combined or "failed" in combined

    def test_no_args_exits_nonzero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["download"])
        assert result.exit_code != 0


class TestDownloadAll:
    """download --all should attempt every downloadable distro."""

    def test_calls_urlretrieve_for_each_distro(self, tmp_path):
        from nightmare_loader.distros import DISTROS
        downloadable_count = sum(
            1 for cfg in DISTROS.values() if cfg.get("download_url")
        )

        def _create_file(url, dest, reporthook=None):
            Path(dest).write_bytes(b"fake")

        runner = CliRunner()
        with patch("urllib.request.urlretrieve", side_effect=_create_file) as mock_get:
            result = runner.invoke(
                cli, ["download", "--all", "--out", str(tmp_path)]
            )
        assert result.exit_code == 0, result.output
        assert mock_get.call_count == downloadable_count


# ---------------------------------------------------------------------------
# nightmare-loader kit
# ---------------------------------------------------------------------------

class TestKitList:
    """kit (no --download) should print the full kit plan."""

    def test_shows_all_categories(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["kit"])
        assert result.exit_code == 0, result.output
        assert "repair" in result.output.lower()
        assert "desktop" in result.output.lower()
        assert "security" in result.output.lower()
        assert "advanced" in result.output.lower()

    def test_shows_manual_windows_section(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["kit"])
        assert result.exit_code == 0
        assert "Manual" in result.output
        assert "www.microsoft.com/en-us/software-download/windows11" in result.output

    def test_category_filter(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["kit", "--category", "repair"])
        assert result.exit_code == 0
        # repair category should appear
        assert "repair" in result.output.lower()
        # desktop entries should NOT appear in the auto-download section
        assert "ubuntu" not in result.output.lower()

    def test_shows_totals(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["kit"])
        assert result.exit_code == 0
        assert "total" in result.output.lower()
        assert "GB" in result.output


class TestKitDownload:
    """kit --download should use _download_iso_url for each auto-downloadable entry."""

    def test_downloads_all_kit_isos(self, tmp_path):
        from nightmare_loader.distros import DISTROS, KIT_64GB
        downloadable_count = sum(
            1 for key, _, _, _ in KIT_64GB
            if DISTROS.get(key, {}).get("download_url")
        )

        def _create_file(url, dest, reporthook=None):
            Path(dest).write_bytes(b"fake")

        runner = CliRunner()
        with patch("urllib.request.urlretrieve", side_effect=_create_file) as mock_get:
            result = runner.invoke(
                cli, ["kit", "--download", "--out", str(tmp_path)]
            )
        assert result.exit_code == 0, result.output
        assert mock_get.call_count == downloadable_count

    def test_download_failure_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        with patch(
            "urllib.request.urlretrieve",
            side_effect=OSError("network error"),
        ):
            result = runner.invoke(
                cli, ["kit", "--download", "--out", str(tmp_path)]
            )
        assert result.exit_code != 0
        combined = result.output
        assert "failed" in combined.lower()

    def test_category_filter_downloads_only_matching(self, tmp_path):
        from nightmare_loader.distros import DISTROS, KIT_64GB
        repair_count = sum(
            1 for key, _, cat, _ in KIT_64GB
            if cat == "repair" and DISTROS.get(key, {}).get("download_url")
        )

        def _create_file(url, dest, reporthook=None):
            Path(dest).write_bytes(b"fake")

        runner = CliRunner()
        with patch("urllib.request.urlretrieve", side_effect=_create_file) as mock_get:
            result = runner.invoke(
                cli,
                ["kit", "--download", "--category", "repair", "--out", str(tmp_path)],
            )
        assert result.exit_code == 0, result.output
        assert mock_get.call_count == repair_count
