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

import contextlib
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from . import __version__
from .drive import (
    DriveError,
    _is_termux,
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
    install_wimboot,
    load_state,
    save_state,
    write_grub_cfg,
)
from .iso import ISOError, get_iso_metadata
from .server import DEFAULT_PORT, start_server


_BYTES_PER_GB = 1_073_741_824

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _termux_nl_exe() -> str:
    """Return the absolute path to the running nightmare-loader executable.

    When nightmare-loader is installed via pip inside Termux, ``sys.argv[0]``
    is the full path (e.g. ``/data/data/com.termux/files/usr/bin/nightmare-loader``).
    Using this absolute path in ``tsu`` invocations avoids "not found" errors
    that occur because ``tsu`` launches a root shell whose ``$PATH`` does not
    include Termux's bin directory.
    """
    if os.path.isabs(sys.argv[0]):
        return sys.argv[0]
    found = shutil.which("nightmare-loader")
    if found:
        return found
    return sys.argv[0]


def _termux_bash() -> str:
    """Return the absolute path to bash for use with ``tsu`` on Termux.

    ``tsu`` strips ``$PATH`` to a minimal root environment, so we must supply
    the full path to bash (e.g. ``/data/data/com.termux/files/usr/bin/bash``)
    rather than relying on name resolution.
    """
    found = shutil.which("bash")
    if found:
        return found
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    return f"{prefix}/bin/bash"


def _require_root() -> None:
    """Exit with an error if not running as root."""
    if os.geteuid() != 0:
        if _is_termux():
            nl = _termux_nl_exe()
            click.echo(
                "Error: this command requires root.\n"
                "\n"
                "On a rooted device, install tsu and run:\n"
                "  pkg install tsu\n"
                f"  tsu {nl} ...",
                err=True,
            )
        else:
            click.echo("Error: this command must be run as root (sudo).", err=True)
        sys.exit(1)


def _require_root_or_mount_point(mount_point: str | None) -> None:
    """Require root unless a pre-mounted path is supplied.

    On Android/Termux without root, the USB drive may already be mounted by
    Android (e.g. at ``/storage/XXXX-XXXX/`` via USB OTG).  Passing
    ``--mount-point`` lets the command use that path directly and skip the
    ``mount``/``umount`` system calls that require root.
    """
    if mount_point:
        return  # pre-mounted path supplied – no root needed
    if os.geteuid() != 0:
        if _is_termux():
            nl = _termux_nl_exe()
            click.echo(
                "Error: this command requires root to mount the drive.\n"
                "\n"
                "On a rooted device:\n"
                "  pkg install tsu\n"
                f"  tsu {nl} COMMAND DEVICE\n"
                "\n"
                "Without root, if Android has already mounted the drive\n"
                "(e.g. USB OTG at /storage/XXXX-XXXX), use --mount-point:\n"
                "  nightmare-loader COMMAND DEVICE --mount-point /storage/XXXX-XXXX",
                err=True,
            )
        else:
            click.echo(
                "Error: this command must be run as root (sudo).\n"
                "If the drive is already mounted, you may also use:\n"
                "  nightmare-loader COMMAND DEVICE --mount-point /path/to/mount",
                err=True,
            )
        sys.exit(1)


def _with_mount(device: str, partition: str):
    """Context manager that mounts *partition* and yields the mount-point path."""

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


@contextlib.contextmanager
def _open_drive(device: str, mount_point: str | None):
    """Yield the filesystem root for *device*.

    If *mount_point* is given the path is used directly (no mounting or
    unmounting occurs).  Otherwise the first partition of *device* is
    mounted in a temporary directory.
    """
    if mount_point:
        mp = Path(mount_point)
        if not mp.is_dir():
            click.echo(f"Error: --mount-point '{mount_point}' is not a directory.", err=True)
            sys.exit(1)
        yield mp
    else:
        partition = _partition_name(device, 1)
        with _with_mount(device, partition) as mp:
            yield mp


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
            size_gb = int(info["size"]) / _BYTES_PER_GB
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
            # Download wimboot for Windows PE boot support (BIOS + UEFI)
            click.echo("Downloading wimboot for Windows PE support…")
            if not install_wimboot(mp):
                click.echo(
                    "  Warning: wimboot download failed (no internet?). "
                    "Windows PE ISOs will not boot until wimboot is installed manually.\n"
                    "  Place wimboot at boot/grub/wimboot (BIOS) and "
                    "boot/grub/wimboot.efi (UEFI) on the drive."
                )
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
            # Download wimboot for Windows PE boot support (BIOS + UEFI)
            click.echo("Downloading wimboot for Windows PE support…")
            if not install_wimboot(mp):
                click.echo(
                    "  Warning: wimboot download failed (no internet?). "
                    "Windows PE ISOs will not boot until wimboot is installed manually.\n"
                    "  Place wimboot at boot/grub/wimboot (BIOS) and "
                    "boot/grub/wimboot.efi (UEFI) on the drive."
                )
            write_grub_cfg(mp, [], label=label)
            save_state(mp, {"entries": [], "label": label})

    click.echo(f"Done. Drive {device} is ready. Add ISOs with:")
    if _is_termux():
        nl = _termux_nl_exe()
        click.echo(f"  tsu {nl} add {device} <path-to.iso>")
        click.echo(
            "\nWithout root, if Android mounts the drive at /storage/XXXX-XXXX, use:\n"
            f"  nightmare-loader add {device} <path-to.iso> --mount-point /storage/XXXX-XXXX"
        )
    else:
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
@click.option(
    "--mount-point", "-m", default=None, metavar="PATH",
    help=(
        "Use PATH as the already-mounted drive root instead of mounting DEVICE "
        "(useful on Android/Termux without root when the drive is mounted by Android, "
        "e.g. /storage/XXXX-XXXX)."
    ),
)
def add_iso(device: str, iso_path: str, label: str | None, copy: bool,
            mount_point: str | None) -> None:
    """
    Add ISO_PATH to DEVICE.

    The ISO is copied into the /isos directory on the drive and a new GRUB
    menu entry is appended.

    \b
    On Android/Termux without root: if Android has mounted the USB drive
    (e.g. at /storage/XXXX-XXXX), pass --mount-point to skip the root-required
    mount step:
      nightmare-loader add /dev/sda ubuntu.iso --mount-point /storage/XXXX-XXXX
    """
    _require_root_or_mount_point(mount_point)

    iso_path_obj = Path(iso_path)
    click.echo(f"Reading ISO metadata: {iso_path_obj.name}…")
    try:
        meta = get_iso_metadata(iso_path_obj)
    except ISOError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    menu_label = label or f"{meta['distro_label']} ({meta['filename']})"

    with _open_drive(device, mount_point) as mp:
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
@click.option(
    "--mount-point", "-m", default=None, metavar="PATH",
    help="Use PATH as the already-mounted drive root instead of mounting DEVICE.",
)
def remove_iso(device: str, iso_name: str, keep_file: bool,
               mount_point: str | None) -> None:
    """
    Remove ISO_NAME from DEVICE.

    ISO_NAME is the filename of the ISO (e.g. ubuntu-22.04.iso).
    Use 'nightmare-loader list DEVICE' to see registered ISOs.

    \b
    On Android/Termux without root, pass --mount-point PATH if the drive is
    already mounted by Android (e.g. /storage/XXXX-XXXX).
    """
    _require_root_or_mount_point(mount_point)

    with _open_drive(device, mount_point) as mp:
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
@click.option(
    "--mount-point", "-m", default=None, metavar="PATH",
    help=(
        "Use PATH as the already-mounted drive root instead of mounting DEVICE "
        "(no root required when the drive is already mounted, e.g. on Android/Termux)."
    ),
)
def list_isos(device: str, mount_point: str | None) -> None:
    """List all ISOs registered on DEVICE.

    \b
    On Android/Termux without root, pass --mount-point PATH if the drive is
    already mounted by Android (e.g. /storage/XXXX-XXXX).
    """
    _require_root_or_mount_point(mount_point)
    with _open_drive(device, mount_point) as mp:
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
@click.option(
    "--mount-point", "-m", default=None, metavar="PATH",
    help="Use PATH as the already-mounted drive root instead of mounting DEVICE.",
)
def update(device: str, mount_point: str | None) -> None:
    """
    Re-generate grub.cfg on DEVICE from the stored state.

    Useful if grub.cfg was accidentally deleted or if you upgraded
    nightmare-loader and want to apply new default settings.

    \b
    On Android/Termux without root, pass --mount-point PATH if the drive is
    already mounted by Android (e.g. /storage/XXXX-XXXX).
    """
    _require_root_or_mount_point(mount_point)

    with _open_drive(device, mount_point) as mp:
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
        if str(d["size"]).isdigit():
            size_str = f"{int(d['size']) / _BYTES_PER_GB:.1f} GB"
        else:
            size_str = "? GB"
        model = d["model"] or "unknown"
        transport = d["transport"] or "?"
        click.echo(f"  {d['device']}  {model}  ({size_str}, {transport})")


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
              help="Also place a shortcut on ~/Desktop (Linux/Windows). Ignored on Android.")
def install_launcher(desktop: bool) -> None:
    """
    Install a desktop launcher so Nightmare Loader can be started with a
    double-click — no terminal required.

    Linux/macOS: creates a .desktop file in ~/.local/share/applications/.
    Windows: creates a .lnk shortcut in the Start Menu Programs folder.
    Android/Termux: creates a Termux:Widget shortcut script in
    ~/.shortcuts/ so the app can be launched from the home screen widget.

    The launcher (nightmare-loader-gui) automatically requests admin
    privileges when needed (pkexec/sudo on Linux, UAC on Windows).
    On Android, root access via 'tsu' is used when available.
    """
    from .drive import _is_termux
    from .launcher import install_desktop_launcher
    paths = install_desktop_launcher(install_to_desktop=desktop)
    for p in paths:
        click.echo(f"Installed: {p}")
    if _is_termux():
        click.echo(
            "\nDone. Nightmare Loader shortcut installed for Termux:Widget.\n"
            "Add the Termux:Widget to your home screen and tap the script to launch."
        )
    elif sys.platform == "win32":
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
        elif not _is_termux():
            click.echo(
                "A shortcut was also placed on your Desktop. "
                "Right-click → Allow Launching if your file manager asks."
            )


# ---------------------------------------------------------------------------
# nightmare-loader build-iso
# ---------------------------------------------------------------------------

@cli.command("build-iso")
@click.option("--output", "-o", default=None, metavar="PATH",
              help="Output ISO path (default: ./nightmare-loader-live.iso).")
@click.option("--termux", "force_termux", is_flag=True, default=False,
              help="Force the Termux/Android (Alpine + QEMU) build path.")
@click.option("--no-termux", "force_no_termux", is_flag=True, default=False,
              help="Force the native Linux (Debian + debootstrap) build path.")
@click.option("--suite", default=None, metavar="SUITE",
              help="Debian suite for the live rootfs (Linux path only; default: bookworm).")
@click.option("--mirror", default=None, metavar="URL",
              help="Debian mirror URL (Linux path only).")
def build_iso_cmd(
    output: str | None,
    force_termux: bool,
    force_no_termux: bool,
    suite: str | None,
    mirror: str | None,
) -> None:
    """
    Build a bootable Nightmare Loader live ISO (hybrid BIOS + UEFI).

    \b
    Locates build_iso.sh (in the repository checkout or current directory) and
    runs it.  If not already root the command re-invokes itself under sudo
    (Linux) or tsu (Android/Termux).

    \b
    Required tools – Linux host:
      sudo apt install debootstrap squashfs-tools grub-pc-bin \\
                       grub-efi-amd64-bin xorriso mtools
    Required tools – Termux:
      pkg install squashfs-tools xorriso mtools curl cpio gzip qemu-user-x86-64

    \b
    Alternatively, build inside Docker (no root on the host):
      docker build -t nightmare-iso-builder -f Dockerfile.iso-builder .
      docker run --rm --privileged -v "$(pwd)":/out nightmare-iso-builder
    """
    # Locate build_iso.sh.  Search in:
    #   1. The directory that contains this Python file's package root
    #      (works for editable/source installs: pip install -e .)
    #   2. The current working directory
    pkg_dir = Path(__file__).parent
    candidates = [
        pkg_dir.parent / "build_iso.sh",   # source / editable install
        Path("build_iso.sh").resolve(),     # current working directory
    ]

    script: Path | None = None
    for candidate in candidates:
        if candidate.is_file():
            script = candidate.resolve()
            break

    if script is None:
        click.echo(
            "Error: build_iso.sh not found.\n"
            "\n"
            "Run this command from the cloned repository:\n"
            "  git clone https://github.com/NightmareDesigns/Nightmare-loader.git\n"
            "  cd Nightmare-loader\n"
            "  nightmare-loader build-iso\n"
            "\n"
            "Or build with Docker (no root required on the host):\n"
            "  docker build -t nightmare-iso-builder -f Dockerfile.iso-builder .\n"
            "  docker run --rm --privileged -v \"$(pwd)\":/out nightmare-iso-builder",
            err=True,
        )
        sys.exit(1)

    cmd: list[str] = ["bash", str(script)]
    if output:
        cmd += ["--output", output]
    if force_termux:
        cmd.append("--termux")
    if force_no_termux:
        cmd.append("--no-termux")
    if suite:
        cmd += ["--suite", suite]
    if mirror:
        cmd += ["--mirror", mirror]

    if sys.platform == "win32":
        click.echo(
            "Error: building the live ISO is not supported on Windows.\n"
            "\n"
            "Use Docker Desktop (WSL 2 backend) instead:\n"
            "  docker build -t nightmare-iso-builder -f Dockerfile.iso-builder .\n"
            "  docker run --rm --privileged -v \"%cd%\":/out nightmare-iso-builder",
            err=True,
        )
        sys.exit(1)

    if os.geteuid() != 0:
        if _is_termux():
            if shutil.which("tsu"):
                bash_exe = _termux_bash()
                cmd = ["tsu", bash_exe, "-c", shlex.join(cmd)]
            else:
                nl = _termux_nl_exe()
                click.echo(
                    "Error: root is required to build the ISO.\n"
                    "\n"
                    "Install tsu and retry:\n"
                    "  pkg install tsu\n"
                    f"  tsu {nl} build-iso",
                    err=True,
                )
                sys.exit(1)
        else:
            if shutil.which("sudo"):
                cmd = ["sudo"] + cmd
            else:
                click.echo(
                    "Error: root is required to build the ISO.\n"
                    "Run with sudo:\n"
                    "  sudo nightmare-loader build-iso",
                    err=True,
                )
                sys.exit(1)

    sys.exit(subprocess.call(cmd))


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
    * **Android/Termux** – elevation is skipped (root is optional on Termux);
      the server starts and the URL is printed so the user can open it in
      any browser on the device.

    Once running with sufficient privileges, the web UI server is started
    and a browser window is opened automatically (except on Android/Termux
    where ``webbrowser`` is unreliable – the URL is printed instead).
    """
    from .drive import _is_termux
    if _is_termux():
        # On Termux there is no graphical elevation and no reliable webbrowser.
        # Just start the server and tell the user which URL to open.
        click.echo(
            "Nightmare Loader running on Android/Termux.\n"
            f"Open this URL in your browser: http://127.0.0.1:{DEFAULT_PORT}/"
        )
        start_server(open_browser=False)
        return

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
