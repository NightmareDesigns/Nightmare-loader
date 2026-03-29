"""
Nightmare Loader – built-in web UI server.

Provides a ThreadingHTTPServer that:
  • Serves the single-file HTML UI at GET /
  • Exposes a small JSON REST API used by the UI JavaScript

API surface
-----------
GET  /api/drives
GET  /api/isos/<device>          device = URL-encoded, e.g. %2Fdev%2Fsdb
GET  /api/info?path=<iso_path>
POST /api/prepare                body: {device, label, layout}
POST /api/add                    body: {device, iso_path, label?, copy?}
POST /api/remove                 body: {device, iso_name}
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

# ---------------------------------------------------------------------------
# Locate the bundled UI file
# ---------------------------------------------------------------------------

_UI_DIR = Path(__file__).parent / "ui"
_INDEX  = _UI_DIR / "index.html"

DEFAULT_PORT = 8321


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):

    # ── Logging ──────────────────────────────────────────────────────────
    def log_message(self, fmt, *args):  # suppress default stdout logging
        pass

    # ── Routing ──────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path in ("/", "/index.html"):
            self._serve_file(_INDEX, "text/html; charset=utf-8")
        elif path == "/api/drives":
            self._api_drives()
        elif path.startswith("/api/isos"):
            # Support both /api/isos/<device> and /api/isos/ (empty device)
            device = unquote(path[len("/api/isos"):].lstrip("/"))
            self._api_isos(device)
        elif path == "/api/version":
            from . import __version__
            self._json({"version": __version__})
        elif path == "/api/info":
            params = parse_qs(parsed.query)
            iso_path = unquote(params.get("path", [""])[0])
            self._api_info(iso_path)
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        try:
            body = self._read_json_body()
        except Exception as exc:
            self._json({"error": f"Bad request body: {exc}"}, 400)
            return

        if path == "/api/prepare":
            self._api_prepare(body)
        elif path == "/api/add":
            self._api_add(body)
        elif path == "/api/remove":
            self._api_remove(body)
        else:
            self._json({"error": "Not found"}, 404)

    # ── Low-level helpers ─────────────────────────────────────────────
    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length) if length else b"{}"
        return json.loads(raw)

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self._json({"error": "File not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ── API: GET /api/drives ──────────────────────────────────────────
    def _api_drives(self) -> None:
        try:
            from .drive import list_removable_drives
            drives = list_removable_drives()
            self._json({"drives": drives})
        except Exception as exc:
            self._json({"drives": [], "error": str(exc)})

    # ── API: GET /api/isos/<device> ───────────────────────────────────
    def _api_isos(self, device: str) -> None:
        if not device:
            self._json({"device": "", "entries": [], "error": "No device specified"})
            return
        try:
            from .drive import _partition_name, mount, unmount
            from .grub  import load_state

            partition = _partition_name(device, 1)
            with tempfile.TemporaryDirectory(prefix="nl-ui-") as tmp:
                mount(partition, tmp)
                try:
                    state   = load_state(tmp)
                    entries = state.get("entries", [])
                finally:
                    try:
                        unmount(tmp)
                    except Exception:
                        pass
            self._json({"device": device, "entries": entries})
        except Exception as exc:
            self._json({"device": device, "entries": [], "error": str(exc)})

    # ── API: GET /api/info?path=… ─────────────────────────────────────
    def _api_info(self, iso_path: str) -> None:
        if not iso_path:
            self._json({"error": "No path specified"}, 400)
            return
        try:
            from .iso import get_iso_metadata
            meta = get_iso_metadata(iso_path)
            self._json(meta)
        except Exception as exc:
            self._json({"error": str(exc)}, 400)

    # ── API: POST /api/prepare ────────────────────────────────────────
    def _api_prepare(self, body: dict) -> None:
        device = body.get("device", "").strip()
        label  = (body.get("label", "NIGHTMARE") or "NIGHTMARE").strip()[:11].upper()
        layout = body.get("layout", "hybrid").lower()

        if not device:
            self._json({"error": "device is required"}, 400)
            return
        if layout not in ("hybrid", "gpt"):
            self._json({"error": "layout must be 'hybrid' or 'gpt'"}, 400)
            return

        try:
            from .drive import (
                prepare_drive_hybrid, prepare_drive_gpt, mount, unmount,
                _partition_name,
            )
            from .grub import (
                install_grub_bios, install_grub_efi, write_grub_cfg,
                save_state, ISO_DIR,
            )

            if layout == "hybrid":
                partition = prepare_drive_hybrid(device, label=label)
                with tempfile.TemporaryDirectory(prefix="nl-ui-") as mp:
                    mount(partition, mp)
                    try:
                        Path(mp, ISO_DIR).mkdir(parents=True, exist_ok=True)
                        install_grub_bios(device, mp)
                        install_grub_efi(mp, removable=True)
                        write_grub_cfg(mp, [])
                        save_state(mp, {"entries": []})
                    finally:
                        try:
                            unmount(mp)
                        except Exception:
                            pass
            else:
                esp, data = prepare_drive_gpt(device, label=label)
                with tempfile.TemporaryDirectory(prefix="nl-ui-data-") as mp:
                    mount(data, mp)
                    try:
                        Path(mp, ISO_DIR).mkdir(parents=True, exist_ok=True)
                        with tempfile.TemporaryDirectory(prefix="nl-ui-esp-") as esp_mp:
                            mount(esp, esp_mp)
                            try:
                                install_grub_bios(device, mp)
                                install_grub_efi(esp_mp, removable=True)
                            finally:
                                try:
                                    unmount(esp_mp)
                                except Exception:
                                    pass
                        write_grub_cfg(mp, [])
                        save_state(mp, {"entries": []})
                    finally:
                        try:
                            unmount(mp)
                        except Exception:
                            pass

            self._json({"ok": True, "message": f"Drive {device} prepared successfully ({layout})."})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)

    # ── API: POST /api/add ────────────────────────────────────────────
    def _api_add(self, body: dict) -> None:
        device   = body.get("device", "").strip()
        iso_path = body.get("iso_path", "").strip()
        label    = body.get("label") or None
        do_copy  = body.get("copy", True)

        if not device:
            self._json({"error": "device is required"}, 400)
            return
        if not iso_path:
            self._json({"error": "iso_path is required"}, 400)
            return

        try:
            from .iso   import get_iso_metadata, ISOError
            from .drive import _partition_name, mount, unmount
            from .grub  import load_state, save_state, write_grub_cfg, ISO_DIR

            iso_path_obj = Path(iso_path)
            meta         = get_iso_metadata(iso_path_obj)
            menu_label   = label or f"{meta['distro_label']} ({meta['filename']})"

            partition = _partition_name(device, 1)
            with tempfile.TemporaryDirectory(prefix="nl-ui-") as mp:
                mount(partition, mp)
                try:
                    state       = load_state(mp)
                    dest_dir    = Path(mp) / ISO_DIR
                    dest_dir.mkdir(parents=True, exist_ok=True)

                    if do_copy:
                        shutil.copy2(str(iso_path_obj), str(dest_dir / iso_path_obj.name))

                    entry = {
                        **meta,
                        "isofile": f"/{ISO_DIR}/{iso_path_obj.name}",
                        "label":   menu_label,
                    }
                    state["entries"] = [
                        e for e in state["entries"]
                        if e["filename"] != iso_path_obj.name
                    ]
                    state["entries"].append(entry)
                    save_state(mp, state)
                    write_grub_cfg(mp, state["entries"])
                finally:
                    try:
                        unmount(mp)
                    except Exception:
                        pass

            self._json({"ok": True, "message": f"Added '{menu_label}' to {device}."})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)

    # ── API: POST /api/remove ─────────────────────────────────────────
    def _api_remove(self, body: dict) -> None:
        device   = body.get("device", "").strip()
        iso_name = body.get("iso_name", "").strip()

        if not device:
            self._json({"error": "device is required"}, 400)
            return
        if not iso_name:
            self._json({"error": "iso_name is required"}, 400)
            return

        try:
            from .drive import _partition_name, mount, unmount
            from .grub  import load_state, save_state, write_grub_cfg, ISO_DIR

            partition = _partition_name(device, 1)
            with tempfile.TemporaryDirectory(prefix="nl-ui-") as mp:
                mount(partition, mp)
                try:
                    state = load_state(mp)
                    before = len(state["entries"])
                    state["entries"] = [
                        e for e in state["entries"] if e["filename"] != iso_name
                    ]
                    if len(state["entries"]) == before:
                        self._json({"error": f"'{iso_name}' not found on {device}"}, 404)
                        return

                    iso_file = Path(mp) / ISO_DIR / iso_name
                    if iso_file.exists():
                        iso_file.unlink()

                    save_state(mp, state)
                    write_grub_cfg(mp, state["entries"])
                finally:
                    try:
                        unmount(mp)
                    except Exception:
                        pass

            self._json({"ok": True, "message": f"Removed '{iso_name}' from {device}."})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_server(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """
    Start the Nightmare Loader web UI server.

    Parameters
    ----------
    port:
        TCP port to listen on.  Defaults to 8321.
    open_browser:
        If True, open the default system browser automatically after 0.5 s.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url    = f"http://127.0.0.1:{port}"

    print(f"Nightmare Loader UI  →  {url}")
    print("Press Ctrl-C to stop.\n")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
