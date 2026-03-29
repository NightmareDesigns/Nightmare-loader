"""
Tests for nightmare_loader.grub – GRUB config generation and state helpers.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from nightmare_loader.grub import (
    GRUB_CFG,
    GRUB_THEME_DIR,
    ISO_DIR,
    STATE_FILE,
    generate_grub_cfg,
    install_grub_theme,
    load_state,
    save_state,
    write_grub_cfg,
    _linux_entry,
    _windows_entry,
)


# ---------------------------------------------------------------------------
# _linux_entry
# ---------------------------------------------------------------------------

class TestLinuxEntry:
    def test_contains_label(self):
        out = _linux_entry("Ubuntu 22.04", "/isos/ubuntu.iso",
                           "/casper/vmlinuz", "/casper/initrd",
                           "boot=casper iso-scan/filename={isofile}")
        assert 'menuentry "Ubuntu 22.04"' in out

    def test_loopback_command_present(self):
        out = _linux_entry("Test", "/isos/test.iso",
                           "/kernel", "/initrd", "quiet {isofile}")
        assert "loopback loop" in out

    def test_isofile_placeholder_replaced_in_cmdline(self):
        out = _linux_entry("Test", "/isos/test.iso",
                           "/kernel", "/initrd",
                           "iso-scan/filename={isofile}")
        assert "iso-scan/filename=/isos/test.iso" in out

    def test_linux_and_initrd_lines(self):
        out = _linux_entry("Test", "/isos/test.iso",
                           "/casper/vmlinuz", "/casper/initrd", "quiet")
        assert "linux (loop)/casper/vmlinuz" in out
        assert "initrd (loop)/casper/initrd" in out


# ---------------------------------------------------------------------------
# _windows_entry
# ---------------------------------------------------------------------------

class TestWindowsEntry:
    def test_contains_label(self):
        out = _windows_entry("Windows 11", "/isos/win11.iso")
        assert "Windows 11" in out

    def test_loopback_present(self):
        out = _windows_entry("Windows 11", "/isos/win11.iso")
        assert "loopback loop" in out

    def test_wimboot_referenced(self):
        out = _windows_entry("Windows 11", "/isos/win11.iso")
        assert "wimboot" in out


# ---------------------------------------------------------------------------
# generate_grub_cfg
# ---------------------------------------------------------------------------

class TestGenerateGrubCfg:
    def _ubuntu_entry(self):
        return {
            "label": "Ubuntu 22.04",
            "isofile": "/isos/ubuntu-22.04.iso",
            "distro": "ubuntu",
            "distro_label": "Ubuntu",
            "filename": "ubuntu-22.04.iso",
            "kernel": "/casper/vmlinuz",
            "initrd": "/casper/initrd",
            "cmdline": "boot=casper iso-scan/filename={isofile} quiet splash ---",
        }

    def _arch_entry(self):
        return {
            "label": "Arch Linux",
            "isofile": "/isos/archlinux.iso",
            "distro": "arch",
            "distro_label": "Arch Linux",
            "filename": "archlinux.iso",
            "kernel": "/arch/boot/x86_64/vmlinuz-linux",
            "initrd": "/arch/boot/x86_64/initramfs-linux.img",
            "cmdline": "img_dev=/dev/disk/by-label/NIGHTMARE img_loop={isofile} quiet",
        }

    def _windows_entry_dict(self):
        return {
            "label": "Windows 11",
            "isofile": "/isos/win11.iso",
            "distro": "windows",
            "distro_label": "Windows",
            "filename": "win11.iso",
            "kernel": None,
            "initrd": None,
            "cmdline": None,
        }

    def test_empty_entries_returns_valid_cfg(self):
        cfg = generate_grub_cfg([])
        assert "set default=0" in cfg
        assert "set timeout=" in cfg
        assert "Reboot" in cfg
        assert "Power Off" in cfg

    def test_search_command_present_default_label(self):
        cfg = generate_grub_cfg([])
        assert "search --no-floppy --label --set=root NIGHTMARE" in cfg

    def test_search_command_uses_custom_label(self):
        cfg = generate_grub_cfg([], label="MYUSB")
        assert "search --no-floppy --label --set=root MYUSB" in cfg

    def test_gfxterm_wrapped_in_conditional(self):
        cfg = generate_grub_cfg([])
        assert "if loadfont" in cfg
        assert "terminal_output gfxterm" in cfg

    def test_ubuntu_entry_present(self):
        cfg = generate_grub_cfg([self._ubuntu_entry()])
        assert "Ubuntu 22.04" in cfg
        assert "/isos/ubuntu-22.04.iso" in cfg
        assert "loopback loop" in cfg

    def test_multiple_entries(self):
        cfg = generate_grub_cfg([self._ubuntu_entry(), self._arch_entry()])
        assert "Ubuntu 22.04" in cfg
        assert "Arch Linux" in cfg

    def test_windows_uses_wimboot_path(self):
        cfg = generate_grub_cfg([self._windows_entry_dict()])
        assert "wimboot" in cfg

    def test_insmod_loopback_in_header(self):
        cfg = generate_grub_cfg([])
        assert "insmod loopback" in cfg

    def test_cmdline_isofile_expanded(self):
        cfg = generate_grub_cfg([self._ubuntu_entry()])
        assert "iso-scan/filename=/isos/ubuntu-22.04.iso" in cfg


# ---------------------------------------------------------------------------
# write_grub_cfg
# ---------------------------------------------------------------------------

class TestWriteGrubCfg:
    def test_creates_file(self, tmp_path):
        write_grub_cfg(tmp_path, [])
        assert (tmp_path / GRUB_CFG).exists()

    def test_creates_parent_dirs(self, tmp_path):
        deep = tmp_path / "sub" / "nested"
        write_grub_cfg(deep, [])
        assert (deep / GRUB_CFG).exists()

    def test_content_written(self, tmp_path):
        entry = {
            "label": "Test ISO",
            "isofile": "/isos/test.iso",
            "distro": "ubuntu",
            "distro_label": "Ubuntu",
            "filename": "test.iso",
            "kernel": "/casper/vmlinuz",
            "initrd": "/casper/initrd",
            "cmdline": "boot=casper iso-scan/filename={isofile} quiet",
        }
        write_grub_cfg(tmp_path, [entry])
        content = (tmp_path / GRUB_CFG).read_text()
        assert "Test ISO" in content

    def test_custom_label_written_to_search_command(self, tmp_path):
        write_grub_cfg(tmp_path, [], label="CUSTOM")
        content = (tmp_path / GRUB_CFG).read_text()
        assert "search --no-floppy --label --set=root CUSTOM" in content

    def test_default_label_nightmare_in_search_command(self, tmp_path):
        write_grub_cfg(tmp_path, [])
        content = (tmp_path / GRUB_CFG).read_text()
        assert "search --no-floppy --label --set=root NIGHTMARE" in content


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

class TestState:
    def test_load_state_missing_returns_empty(self, tmp_path):
        state = load_state(tmp_path)
        assert state == {"entries": []}

    def test_save_and_load_roundtrip(self, tmp_path):
        original = {"entries": [{"filename": "test.iso", "label": "Test"}]}
        save_state(tmp_path, original)
        loaded = load_state(tmp_path)
        assert loaded == original

    def test_state_file_is_json(self, tmp_path):
        save_state(tmp_path, {"entries": []})
        raw = (tmp_path / STATE_FILE).read_text()
        parsed = json.loads(raw)
        assert "entries" in parsed

    def test_state_saved_in_root(self, tmp_path):
        save_state(tmp_path, {"entries": []})
        assert (tmp_path / STATE_FILE).exists()


# ---------------------------------------------------------------------------
# install_grub_theme
# ---------------------------------------------------------------------------

class TestInstallGrubTheme:
    def test_creates_theme_directory(self, tmp_path):
        install_grub_theme(tmp_path)
        assert (tmp_path / GRUB_THEME_DIR).is_dir()

    def test_writes_theme_txt(self, tmp_path):
        dest = install_grub_theme(tmp_path)
        assert dest.name == "theme.txt"
        assert dest.exists()

    def test_theme_contains_nightmare_title(self, tmp_path):
        dest = install_grub_theme(tmp_path)
        content = dest.read_text()
        assert "NIGHTMARE LOADER" in content

    def test_theme_has_green_menu_color(self, tmp_path):
        dest = install_grub_theme(tmp_path)
        content = dest.read_text()
        # Green item color for matrix aesthetic
        assert "item_color" in content

    def test_grub_cfg_references_theme(self, tmp_path):
        cfg = generate_grub_cfg([])
        assert "themes/nightmare/theme.txt" in cfg
