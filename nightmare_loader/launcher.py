"""
Desktop launcher helpers for Nightmare Loader.

Provides :func:`install_desktop_launcher` which installs a shortcut so
users can launch Nightmare Loader with a double-click instead of typing a
terminal command.

* **Linux / macOS** — writes a ``.desktop`` file to
  ``~/.local/share/applications/`` (and optionally ``~/Desktop/``).
* **Windows** — creates ``.lnk`` shortcuts in the Start Menu
  ``Programs`` folder (and optionally on the Desktop) using PowerShell.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
from pathlib import Path

# Source .desktop template bundled with the package
_DESKTOP_SRC = Path(__file__).parent / "assets" / "nightmare-loader.desktop"

# Standard XDG locations (Linux/macOS)
_XDG_APPS_DIR = Path.home() / ".local" / "share" / "applications"
_DESKTOP_DIR  = Path.home() / "Desktop"


def install_desktop_launcher(
    install_to_desktop: bool = False,
    executable: str | None = None,
) -> list[Path]:
    """
    Install the Nightmare Loader desktop launcher for the current user.

    On Linux/macOS creates a ``.desktop`` file in
    ``~/.local/share/applications/``.  On Windows creates a ``.lnk`` shortcut
    in the user's Start Menu Programs folder.  Optionally also places a
    shortcut on ``~/Desktop`` on both platforms.

    Parameters
    ----------
    install_to_desktop:
        If ``True``, also create a launcher on ``~/Desktop``.
    executable:
        Override the target executable path.  Defaults to the
        ``nightmare-loader-gui`` script resolved from the current Python
        environment.

    Returns
    -------
    list[Path]
        Paths of every shortcut file written.
    """
    if sys.platform == "win32":
        return _install_windows_shortcut(
            install_to_desktop=install_to_desktop,
            executable=executable,
        )
    return _install_linux_desktop(
        install_to_desktop=install_to_desktop,
        executable=executable,
    )


# ---------------------------------------------------------------------------
# Linux / macOS implementation
# ---------------------------------------------------------------------------

def _install_linux_desktop(
    install_to_desktop: bool = False,
    executable: str | None = None,
) -> list[Path]:
    exec_path = executable or _find_gui_executable()
    template  = _DESKTOP_SRC.read_text(encoding="utf-8")
    content   = template.replace("Exec=nightmare-loader-gui", f"Exec={exec_path}")

    written: list[Path] = []

    # Always install to applications menu
    _XDG_APPS_DIR.mkdir(parents=True, exist_ok=True)
    menu_dest = _XDG_APPS_DIR / "nightmare-loader.desktop"
    menu_dest.write_text(content, encoding="utf-8")
    written.append(menu_dest)

    # Optionally install to Desktop
    if install_to_desktop and _DESKTOP_DIR.exists():
        desktop_dest = _DESKTOP_DIR / "nightmare-loader.desktop"
        desktop_dest.write_text(content, encoding="utf-8")
        # Mark the desktop file as trusted / executable so file managers
        # show it as a launcher rather than a plain text file.
        desktop_dest.chmod(desktop_dest.stat().st_mode | stat.S_IXUSR)
        written.append(desktop_dest)

    return written


# ---------------------------------------------------------------------------
# Windows implementation
# ---------------------------------------------------------------------------

def _install_windows_shortcut(
    install_to_desktop: bool = False,
    executable: str | None = None,
) -> list[Path]:
    """Create Windows ``.lnk`` shortcuts using PowerShell WScript.Shell."""
    exec_path = executable or _find_gui_executable()

    # Start Menu > Programs
    start_menu = _windows_start_menu_dir()
    start_menu.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    menu_lnk = start_menu / "Nightmare Loader.lnk"
    _create_lnk(menu_lnk, exec_path, "Nightmare Loader – Multi-ISO USB Boot Creator")
    written.append(menu_lnk)

    if install_to_desktop:
        desktop = Path.home() / "Desktop"
        if desktop.exists():
            desktop_lnk = desktop / "Nightmare Loader.lnk"
            _create_lnk(desktop_lnk, exec_path, "Nightmare Loader – Multi-ISO USB Boot Creator")
            written.append(desktop_lnk)

    return written


def _windows_start_menu_dir() -> Path:
    """Return the per-user Start Menu Programs folder."""
    import os
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _create_lnk(dest: Path, target: str, description: str) -> None:
    """
    Create a Windows ``.lnk`` shortcut at *dest* pointing to *target*.

    Uses PowerShell's ``WScript.Shell`` COM object – no third-party libraries
    required.
    """
    ps = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{dest}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.Description = '{description}'; "
        f"$s.Save()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OSError(f"Failed to create shortcut: {result.stderr.strip()}")


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _find_gui_executable() -> str:
    """
    Return the absolute path of the ``nightmare-loader-gui`` script.

    Falls back to ``nightmare-loader-gui`` (bare name) if the script is not
    yet installed, so the shortcut still works once the package is on PATH.
    """
    # On Windows the entry-point script is a .exe; on other platforms no extension
    if sys.platform == "win32":
        name = "nightmare-loader-gui.exe"
        script = shutil.which(name)
    else:
        name = "nightmare-loader-gui"
        script = shutil.which(name)
    if script:
        return script
    # Try the same directory as the currently running Python interpreter
    py_bin = Path(sys.executable).parent / name
    if py_bin.exists():
        return str(py_bin)
    return name
