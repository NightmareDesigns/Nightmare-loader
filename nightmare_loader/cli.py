"""
Nightmare Loader – CLI interface.

Usage examples::

    # Prepare a USB drive (wipes data!) and install GRUB
    sudo nightmare-loader prepare /dev/sdb

    # Add an ISO to the drive
    sudo nightmare-loader add /dev/sdb ~/Downloads/ubuntu-22.04.iso

    # List ISOs registered on the drive
    nightmare-loader list /dev/sdb

    # Remove an ISO from the drive
    sudo nightmare-loader remove /dev/sdb ubuntu-22.04.iso

    # Re-generate grub.cfg from the state file (useful after manual edits)
    sudo nightmare-loader update /dev/sdb

    # Show detected distribution for an ISO (no drive needed)
    nightmare-loader info ~/Downloads/ubuntu-22.04.iso
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

import click

from . import __version__
from .drive import (
    DriveError,
    get_drive_info,
    list_removable_drives,
    mount,
    prepare_drive_gpt,
    prepare_drive_hybrid,
    unmount,
    _partition_name,
)
from .grub import (
    ISO_DIR,
    install_grub_bios,
    install_grub_efi,
    install_grub_theme,
    load_state,
    save_state,
    write_grub_cfg,
)
from .iso import ISOError, get_iso_metadata
from .server import DEFAULT_PORT, start_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_root() -> None:
    if os.geteuid() != 0:
        click.echo("Error: this command must be run as root (sudo).", err=True)
        sys.exit(1)


def _with_mount(device: str, partition: str):
    """Context manager that mounts *partition* and yields the mount-point path."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        with tempfile.TemporaryDirectory(prefix="nightmare-loader-") as tmp:
            mount(partition, tmp)
            try:
                yield Path(tmp)
            finally:
                try:
                    unmount(tmp)
                except Exception:
                    pass

    return _ctx()


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="nightmare-loader")
def cli() -> None:
    """Nightmare Loader – create multi-ISO bootable USB drives (UEFI + legacy BIOS)."""


# ---------------------------------------------------------------------------
# nightmare-loader prepare
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("device")
@click.option(
    "--layout",
    type=click.Choice(["hybrid", "gpt"], case_sensitive=False),
    default="hybrid",
    show_default=True,
    help=(
        "Partition layout: 'hybrid' = single FAT32 partition (MBR, works "
        "everywhere); 'gpt' = separate ESP + data partition."
    ),
)
@click.option("--label", default="NIGHTMARE", show_default=True,
              help="Volume label for the data partition (max 11 chars).")
@click.option("--yes", "-y", is_flag=True, default=False,
              help="Skip the confirmation prompt.")
def prepare(device: str, layout: str, label: str, yes: bool) -> None:
    """
    Partition, format, and install GRUB on DEVICE.

    \b
    DEVICE  Block device path, e.g. /dev/sdb
            Use 'nightmare-loader drives' to list removable drives.

    WARNING: All data on DEVICE will be erased.
    """
    _require_root()

    # Confirm
    if not yes:
        try:
            info = get_drive_info(device)
            size_gb = int(info["size"]) / 1_073_741_824
            model = info["model"] or "unknown model"
            click.echo(
                f"About to erase {device} ({model}, {size_gb:.1f} GB) "
                f"and install Nightmare Loader."
            )
        except Exception:
            click.echo(f"About to erase {device} and install Nightmare Loader.")
        click.confirm("Continue?", abort=True)

    click.echo(f"Preparing {device} with '{layout}' layout…")

    if layout == "hybrid":
        partition = prepare_drive_hybrid(device, label=label)
        with _with_mount(device, partition) as mp:
            iso_dir = mp / ISO_DIR
            iso_dir.mkdir(parents=True, exist_ok=True)
            # Install GRUB for legacy BIOS
            click.echo("Installing GRUB (legacy BIOS)…")
            install_grub_bios(device, mp)
            # Install GRUB for UEFI
            click.echo("Installing GRUB (UEFI)…")
            install_grub_efi(mp, removable=True)
            # Install the Nightmare Loader themed pre-loader
            install_grub_theme(mp)
            # Write initial (empty) grub.cfg – pass label so the search
            # command in the header matches the FAT volume label.
            write_grub_cfg(mp, [], label=label)
            save_state(mp, {"entries": [], "label": label})
    else:  # gpt
        esp, data = prepare_drive_gpt(device, label=label)
        with _with_mount(device, data) as mp:
            iso_dir = mp / ISO_DIR
            iso_dir.mkdir(parents=True, exist_ok=True)
            # For GPT we mount the ESP separately to install the EFI shim
            with tempfile.TemporaryDirectory(prefix="nightmare-esp-") as esp_mp:
                mount(esp, esp_mp)
                try:
                    click.echo("Installing GRUB (legacy BIOS)…")
                    install_grub_bios(device, mp)
                    click.echo("Installing GRUB (UEFI) on ESP…")
                    install_grub_efi(esp_mp, removable=True)
                finally:
                    try:
                        unmount(esp_mp)
                    except Exception:
                        pass
            # Install the Nightmare Loader themed pre-loader
            install_grub_theme(mp)
            write_grub_cfg(mp, [], label=label)
            save_state(mp, {"entries": [], "label": label})

    click.echo(f"Done. Drive {device} is ready. Add ISOs with:")
    click.echo(f"  sudo nightmare-loader add {device} <path-to.iso>")


# ---------------------------------------------------------------------------
# nightmare-loader add
# ---------------------------------------------------------------------------

@cli.command("add")
@click.argument("device")
@click.argument("iso_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--label", default=None,
              help="Custom menu label for this entry (default: auto-detected).")
@click.option("--copy/--no-copy", default=True, show_default=True,
              help="Copy the ISO to the drive (--no-copy to register an already-copied ISO).")
def add_iso(device: str, iso_path: str, label: str | None, copy: bool) -> None:
    """
    Add ISO_PATH to DEVICE.

    The ISO is copied into the /isos directory on the drive and a new GRUB
    menu entry is appended.
    """
    _require_root()

    iso_path_obj = Path(iso_path)
    click.echo(f"Reading ISO metadata: {iso_path_obj.name}…")
    try:
        meta = get_iso_metadata(iso_path_obj)
    except ISOError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    menu_label = label or f"{meta['distro_label']} ({meta['filename']})"

    partition = _partition_name(device, 1)
    with _with_mount(device, partition) as mp:
        state = load_state(mp)
        iso_dest_dir = mp / ISO_DIR
        iso_dest_dir.mkdir(parents=True, exist_ok=True)
        dest = iso_dest_dir / iso_path_obj.name

        # Check for duplicates
        existing = [e for e in state["entries"] if e["filename"] == iso_path_obj.name]
        if existing:
            click.echo(f"Warning: {iso_path_obj.name} is already registered on this drive.")
            if not click.confirm("Replace it?"):
                click.echo("Aborted.")
                return

        if copy:
            click.echo(f"Copying {iso_path_obj.name} ({meta['size_bytes'] / 1e6:.0f} MB)…")
            shutil.copy2(str(iso_path_obj), str(dest))

        entry = {
            **meta,
            "isofile": f"/{ISO_DIR}/{iso_path_obj.name}",
            "label": menu_label,
        }
        # Remove old entry with same filename before adding updated one
        state["entries"] = [e for e in state["entries"] if e["filename"] != iso_path_obj.name]
        state["entries"].append(entry)
        save_state(mp, state)
        drive_label = state.get("label", "NIGHTMARE")
        write_grub_cfg(mp, state["entries"], label=drive_label)

    click.echo(f"Added '{menu_label}' to {device}.")


# ---------------------------------------------------------------------------
# nightmare-loader remove
# ---------------------------------------------------------------------------

@cli.command("remove")
@click.argument("device")
@click.argument("iso_name")
@click.option("--keep-file", is_flag=True, default=False,
              help="Do not delete the ISO file, just remove the menu entry.")
def remove_iso(device: str, iso_name: str, keep_file: bool) -> None:
    """
    Remove ISO_NAME from DEVICE.

    ISO_NAME is the filename of the ISO (e.g. ubuntu-22.04.iso).
    Use 'nightmare-loader list DEVICE' to see registered ISOs.
    """
    _require_root()

    partition = _partition_name(device, 1)
    with _with_mount(device, partition) as mp:
        state = load_state(mp)
        before = len(state["entries"])
        state["entries"] = [e for e in state["entries"] if e["filename"] != iso_name]

        if len(state["entries"]) == before:
            click.echo(f"Error: '{iso_name}' is not registered on {device}.", err=True)
            sys.exit(1)

        if not keep_file:
            iso_file = mp / ISO_DIR / iso_name
            if iso_file.exists():
                iso_file.unlink()
                click.echo(f"Deleted {iso_file}.")

        save_state(mp, state)
        drive_label = state.get("label", "NIGHTMARE")
        write_grub_cfg(mp, state["entries"], label=drive_label)

    click.echo(f"Removed '{iso_name}' from {device}.")


# ---------------------------------------------------------------------------
# nightmare-loader list
# ---------------------------------------------------------------------------

@cli.command("list")
@click.argument("device")
def list_isos(device: str) -> None:
    """List all ISOs registered on DEVICE."""
    partition = _partition_name(device, 1)
    with _with_mount(device, partition) as mp:
        state = load_state(mp)
        entries = state.get("entries", [])

    if not entries:
        click.echo(f"No ISOs registered on {device}.")
        return

    click.echo(f"ISOs on {device}:")
    for i, entry in enumerate(entries, 1):
        size_mb = entry.get("size_bytes", 0) / 1_048_576
        click.echo(
            f"  {i}. {entry['label']}\n"
            f"       File  : {entry['filename']}\n"
            f"       Distro: {entry['distro']} ({entry['distro_label']})\n"
            f"       Size  : {size_mb:.0f} MB\n"
        )


# ---------------------------------------------------------------------------
# nightmare-loader update
# ---------------------------------------------------------------------------

@cli.command("update")
@click.argument("device")
def update(device: str) -> None:
    """
    Re-generate grub.cfg on DEVICE from the stored state.

    Useful if grub.cfg was accidentally deleted or if you upgraded
    nightmare-loader and want to apply new default settings.
    """
    _require_root()

    partition = _partition_name(device, 1)
    with _with_mount(device, partition) as mp:
        state = load_state(mp)
        drive_label = state.get("label", "NIGHTMARE")
        cfg_path = write_grub_cfg(mp, state["entries"], label=drive_label)

    click.echo(f"Updated {cfg_path}.")


# ---------------------------------------------------------------------------
# nightmare-loader drives
# ---------------------------------------------------------------------------

@cli.command("drives")
def list_drives() -> None:
    """List removable drives (USB sticks, etc.) available on this machine."""
    try:
        drives = list_removable_drives()
    except DriveError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if not drives:
        click.echo("No removable drives found.")
        return

    click.echo("Removable drives:")
    for d in drives:
        size_gb = int(d["size"]) / 1_073_741_824 if str(d["size"]).isdigit() else "?"
        model = d["model"] or "unknown"
        transport = d["transport"] or "?"
        click.echo(f"  {d['device']}  {model}  ({size_gb:.1f} GB, {transport})")


# ---------------------------------------------------------------------------
# nightmare-loader info
# ---------------------------------------------------------------------------

@cli.command("info")
@click.argument("iso_path", type=click.Path(exists=True, dir_okay=False))
def iso_info(iso_path: str) -> None:
    """
    Show detected distribution info for ISO_PATH without touching any drive.
    """
    try:
        meta = get_iso_metadata(iso_path)
    except ISOError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"File    : {meta['filename']}")
    click.echo(f"Label   : {meta['label']}")
    click.echo(f"Size    : {meta['size_bytes'] / 1_048_576:.0f} MB")
    click.echo(f"Distro  : {meta['distro']} ({meta['distro_label']})")
    click.echo(f"Kernel  : {meta['kernel']}")
    click.echo(f"Initrd  : {meta['initrd']}")
    click.echo(f"Cmdline : {meta['cmdline']}")


# ---------------------------------------------------------------------------
# nightmare-loader ui
# ---------------------------------------------------------------------------

@cli.command("ui")
@click.option("--port", "-p", default=DEFAULT_PORT, show_default=True,
              help="TCP port for the web UI server.")
@click.option("--no-browser", is_flag=True, default=False,
              help="Do not open the browser automatically.")
def web_ui(port: int, no_browser: bool) -> None:
    """
    Launch the Nightmare Loader web UI.

    Opens a local web server and (by default) a browser window showing
    the full graphical interface for managing drives and ISOs.
    """
    start_server(port=port, open_browser=not no_browser)


# ---------------------------------------------------------------------------
# nightmare-loader install-launcher
# ---------------------------------------------------------------------------

@cli.command("install-launcher")
@click.option("--desktop", is_flag=True, default=False,
              help="Also place a shortcut on ~/Desktop (Linux) or Desktop (Windows).")
def install_launcher(desktop: bool) -> None:
    """
    Install a desktop launcher so Nightmare Loader can be started with a
    double-click — no terminal required.

    Linux/macOS: creates a .desktop file in ~/.local/share/applications/.
    Windows: creates a .lnk shortcut in the Start Menu Programs folder.

    The launcher (nightmare-loader-gui) automatically requests admin
    privileges when needed (pkexec/sudo on Linux, UAC on Windows).
    """
    from .launcher import install_desktop_launcher
    paths = install_desktop_launcher(install_to_desktop=desktop)
    for p in paths:
        click.echo(f"Installed: {p}")
    if sys.platform == "win32":
        click.echo(
            "\nDone. Nightmare Loader is now in your Start Menu.\n"
            "It will request administrator access via UAC when launched."
        )
    else:
        click.echo(
            "\nDone. You can now launch Nightmare Loader from your application menu."
        )
    if desktop:
        if sys.platform == "win32":
            click.echo("A shortcut was also placed on your Desktop.")
        else:
            click.echo(
                "A shortcut was also placed on your Desktop. "
                "Right-click → Allow Launching if your file manager asks."
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cli()


def gui_main() -> None:
    """
    GUI entry-point launched by the desktop shortcut (``nightmare-loader-gui``).

    * **Linux/macOS** – if not already root, re-executes itself with
      ``pkexec`` / ``kdesudo`` / ``gksudo`` (graphical polkit prompt), or
      falls back to ``sudo`` inside a terminal emulator.
    * **Windows** – if not already running as administrator, re-launches
      itself with the ``runas`` verb via ``ShellExecuteW`` (triggers UAC
      prompt) and exits the current process.

    Once running with sufficient privileges, the web UI server is started
    and a browser window is opened automatically.
    """
    if sys.platform == "win32":
        _ensure_admin_windows()
    elif os.geteuid() != 0:
        self_args = [sys.argv[0]] + sys.argv[1:]
        # Preference order for graphical privilege elevation
        for tool in ("pkexec", "kdesudo", "gksudo"):
            if shutil.which(tool):
                os.execvp(tool, [tool] + self_args)
                # os.execvp replaces the current process – code below is
                # only reached if execvp fails, which is extremely rare.

        # None of the graphical tools found – open a terminal with sudo
        # Build the command as a proper list to avoid shell injection
        sudo_argv = ["sudo"] + self_args
        sudo_cmd  = " ".join(shlex.quote(a) for a in sudo_argv)
        pause_cmd = sudo_cmd + "; echo; read -rp 'Press Enter to close…'"
        for term in (
            "x-terminal-emulator",
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "xterm",
        ):
            if shutil.which(term):
                if term == "gnome-terminal":
                    os.execvp(term, [term, "--", "bash", "-c", pause_cmd])
                else:
                    os.execvp(term, [term, "-e", "bash", "-c", pause_cmd])

    # Running with sufficient privileges (or elevation succeeded) – start the server
    start_server(open_browser=True)


def _ensure_admin_windows() -> None:
    """
    On Windows, re-launch as administrator via UAC if not already elevated.

    Uses ``ctypes.windll.shell32.ShellExecuteW`` with the ``runas`` verb
    which triggers the standard UAC consent prompt.  The current
    (un-elevated) process exits immediately after spawning the elevated one.
    """
    import ctypes
    try:
        is_admin: bool = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError:
        is_admin = False

    if not is_admin:
        # Re-launch elevated; ShellExecuteW returns ≤32 on failure
        # subprocess.list2cmdline() properly escapes args for Windows
        import subprocess as _sp
        args_str = _sp.list2cmdline(sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,          # hwnd
            "runas",       # verb – triggers UAC
            sys.executable,
            args_str,
            None,          # working directory (inherit)
            1,             # nShowCmd = SW_NORMAL
        )
        if ret <= 32:
            click.echo(
                "Administrator access is required to manage USB drives.\n"
                "Please right-click the shortcut and choose 'Run as administrator'.",
                err=True,
            )
        sys.exit(0)


if __name__ == "__main__":
    main()
