"""
Desktop launcher helpers for Nightmare Loader.

Provides :func:`install_desktop_launcher` which installs a ``.desktop``
file so users can launch Nightmare Loader with a double-click instead of
typing a terminal command.
"""

from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path

# Source .desktop template bundled with the package
_DESKTOP_SRC = Path(__file__).parent / "assets" / "nightmare-loader.desktop"

# Standard XDG locations
_XDG_APPS_DIR = Path.home() / ".local" / "share" / "applications"
_DESKTOP_DIR  = Path.home() / "Desktop"


def install_desktop_launcher(
    install_to_desktop: bool = False,
    executable: str | None = None,
) -> list[Path]:
    """
    Install the Nightmare Loader desktop launcher for the current user.

    Creates a ``.desktop`` file in ``~/.local/share/applications/`` so the
    app appears in the system application menu.  Optionally also places a
    shortcut on ``~/Desktop``.

    Parameters
    ----------
    install_to_desktop:
        If ``True``, also copy the launcher to ``~/Desktop`` for a visible
        shortcut icon.
    executable:
        Override the ``Exec=`` value in the desktop file.  Defaults to the
        ``nightmare-loader-gui`` script resolved from the current Python
        environment.

    Returns
    -------
    list[Path]
        Paths of every ``.desktop`` file written.
    """
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


def _find_gui_executable() -> str:
    """
    Return the absolute path of the ``nightmare-loader-gui`` script.

    Falls back to ``nightmare-loader-gui`` (bare name) if the script is not
    yet installed, so the desktop file still works once the package is
    installed to PATH.
    """
    script = shutil.which("nightmare-loader-gui")
    if script:
        return script
    # Try the same directory as the currently running Python interpreter
    py_bin = Path(sys.executable).parent / "nightmare-loader-gui"
    if py_bin.exists():
        return str(py_bin)
    return "nightmare-loader-gui"
