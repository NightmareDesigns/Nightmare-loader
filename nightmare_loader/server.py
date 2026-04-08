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
GET  /api/browse?path=<dir>      list files/dirs (file manager)
GET  /api/update/check           check GitHub for latest release
GET  /api/wifi/status            current WiFi connection info
GET  /api/wifi/networks          scan for available WiFi networks
GET  /api/download/status?id=…   ISO download progress
POST /api/prepare                body: {device, label, layout}
POST /api/add                    body: {device, iso_path, label?, copy?}
POST /api/remove                 body: {device, iso_name}
POST /api/update/install         install latest release from GitHub
POST /api/wifi/connect           body: {ssid, password?}
POST /api/wifi/disconnect        disconnect current WiFi
POST /api/download/start         body: {url, dest_dir?, filename?}
POST /api/download/cancel        body: {id}
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import urllib.request
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
# In-process ISO download registry  (id → state dict)
# ---------------------------------------------------------------------------

_downloads: dict[str, dict] = {}
_downloads_lock = threading.Lock()


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
        elif path == "/api/root":
            # os.geteuid() is Unix-only; on Windows treat as non-root
            is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
            self._json({"root": is_root})
        elif path == "/api/platform":
            import sys as _sys
            from .drive import _is_termux
            _android = _is_termux()
            self._json({
                "platform": _sys.platform,
                "windows":  _sys.platform == "win32",
                "android":  _android,
            })
        elif path == "/api/info":
            params = parse_qs(parsed.query)
            iso_path = unquote(params.get("path", [""])[0])
            self._api_info(iso_path)
        elif path == "/api/browse":
            params = parse_qs(parsed.query)
            browse_path = unquote(params.get("path", [""])[0])
            self._api_browse(browse_path)
        elif path == "/api/update/check":
            self._api_update_check()
        elif path == "/api/wifi/status":
            self._api_wifi_status()
        elif path == "/api/wifi/networks":
            self._api_wifi_networks()
        elif path == "/api/download/status":
            params = parse_qs(parsed.query)
            dl_id = unquote(params.get("id", [""])[0])
            self._api_download_status(dl_id)
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
        elif path == "/api/update/install":
            self._api_update_install()
        elif path == "/api/wifi/connect":
            self._api_wifi_connect(body)
        elif path == "/api/wifi/disconnect":
            self._api_wifi_disconnect()
        elif path == "/api/download/start":
            self._api_download_start(body)
        elif path == "/api/download/cancel":
            self._api_download_cancel(body)
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
                install_grub_bios, install_grub_efi, install_grub_theme,
                write_grub_cfg, save_state, ISO_DIR,
            )

            if layout == "hybrid":
                partition = prepare_drive_hybrid(device, label=label)
                with tempfile.TemporaryDirectory(prefix="nl-ui-") as mp:
                    mount(partition, mp)
                    try:
                        Path(mp, ISO_DIR).mkdir(parents=True, exist_ok=True)
                        install_grub_bios(device, mp)
                        install_grub_efi(mp, removable=True)
                        install_grub_theme(mp)
                        write_grub_cfg(mp, [], label=label)
                        save_state(mp, {"entries": [], "label": label})
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
                        install_grub_theme(mp)
                        write_grub_cfg(mp, [], label=label)
                        save_state(mp, {"entries": [], "label": label})
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
                    drive_label = state.get("label", "NIGHTMARE")
                    write_grub_cfg(mp, state["entries"], label=drive_label)
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
                    drive_label = state.get("label", "NIGHTMARE")
                    write_grub_cfg(mp, state["entries"], label=drive_label)
                finally:
                    try:
                        unmount(mp)
                    except Exception:
                        pass

            self._json({"ok": True, "message": f"Removed '{iso_name}' from {device}."})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)

    # ── API: GET /api/browse?path=… ───────────────────────────────────
    def _api_browse(self, browse_path: str) -> None:
        try:
            # Default to the user's home directory when no path is given
            if not browse_path:
                browse_path = str(Path.home())

            # Reject null bytes (path injection guard)
            if "\x00" in browse_path:
                self._json({"error": "Invalid path"}, 400)
                return

            target = Path(browse_path).resolve()

            if not target.exists() or not target.is_dir():
                self._json({"error": f"Not a directory: {browse_path}"}, 400)
                return

            entries = []
            try:
                items = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except PermissionError:
                self._json({"error": f"Permission denied: {browse_path}"}, 403)
                return

            for item in items:
                try:
                    stat = item.stat()
                    entries.append({
                        "name":  item.name,
                        "path":  str(item),
                        "type":  "file" if item.is_file() else "dir",
                        "size":  stat.st_size if item.is_file() else None,
                    })
                except OSError:
                    pass  # skip entries we cannot stat

            parent = str(target.parent) if target != target.parent else None
            self._json({
                "path":    str(target),
                "parent":  parent,
                "entries": entries,
            })
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    # ── WiFi helpers ──────────────────────────────────────────────────
    @staticmethod
    def _wifi_backend() -> str:
        """Return 'nmcli', 'netsh', or 'none'."""
        import sys as _sys
        if _sys.platform == "win32":
            return "netsh"
        if shutil.which("nmcli"):
            return "nmcli"
        return "none"

    # ── API: GET /api/wifi/status ─────────────────────────────────────
    def _api_wifi_status(self) -> None:
        backend = self._wifi_backend()
        try:
            if backend == "nmcli":
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION",
                     "device", "status"],
                    text=True, timeout=8,
                )
                for line in out.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 4 and parts[1] == "wifi":
                        connected = parts[2] == "connected"
                        self._json({
                            "backend": backend,
                            "connected": connected,
                            "ssid": parts[3] if connected else None,
                            "device": parts[0],
                        })
                        return
                self._json({"backend": backend, "connected": False, "ssid": None})
            elif backend == "netsh":
                out = subprocess.check_output(
                    ["netsh", "wlan", "show", "interfaces"],
                    text=True, timeout=8,
                )
                ssid_match  = __import__("re").search(r"SSID\s*:\s*(.+)", out)
                state_match = __import__("re").search(r"State\s*:\s*(\w+)", out)
                connected   = bool(state_match and state_match.group(1).lower() == "connected")
                self._json({
                    "backend": backend,
                    "connected": connected,
                    "ssid": ssid_match.group(1).strip() if ssid_match and connected else None,
                })
            else:
                self._json({"backend": "none", "connected": None,
                            "error": "No supported WiFi backend found (nmcli / netsh)."})
        except Exception as exc:
            self._json({"backend": backend, "connected": None, "error": str(exc)})

    # ── API: GET /api/wifi/networks ───────────────────────────────────
    def _api_wifi_networks(self) -> None:
        backend = self._wifi_backend()
        try:
            networks = []
            if backend == "nmcli":
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE",
                     "device", "wifi", "list", "--rescan", "yes"],
                    text=True, timeout=20,
                )
                seen: set[str] = set()
                for line in out.splitlines():
                    parts = line.split(":")
                    if len(parts) < 4:
                        continue
                    ssid = parts[0].strip()
                    if not ssid or ssid in seen:
                        continue
                    seen.add(ssid)
                    networks.append({
                        "ssid":    ssid,
                        "signal":  int(parts[1]) if parts[1].isdigit() else 0,
                        "security": parts[2] or "open",
                        "in_use":  parts[3] == "*",
                    })
                networks.sort(key=lambda n: n["signal"], reverse=True)
            elif backend == "netsh":
                out = subprocess.check_output(
                    ["netsh", "wlan", "show", "networks", "mode=bssid"],
                    text=True, timeout=20,
                )
                import re as _re
                for ssid in _re.findall(r"SSID\s*\d*\s*:\s*(.+)", out):
                    ssid = ssid.strip()
                    if ssid:
                        networks.append({"ssid": ssid, "signal": 0,
                                         "security": "unknown", "in_use": False})
            self._json({"backend": backend, "networks": networks})
        except Exception as exc:
            self._json({"backend": backend, "networks": [], "error": str(exc)})

    # ── API: POST /api/wifi/connect ───────────────────────────────────
    def _api_wifi_connect(self, body: dict) -> None:
        ssid     = body.get("ssid", "").strip()
        password = body.get("password", "").strip()
        if not ssid:
            self._json({"error": "ssid is required"}, 400)
            return
        backend = self._wifi_backend()
        try:
            if backend == "nmcli":
                cmd = ["nmcli", "device", "wifi", "connect", ssid]
                if password:
                    cmd += ["password", password]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    self._json({"ok": True, "message": f"Connected to {ssid}."})
                else:
                    self._json({"ok": False,
                                "error": result.stderr.strip() or result.stdout.strip()}, 500)
            elif backend == "netsh":
                result = subprocess.run(
                    ["netsh", "wlan", "connect", f"name={ssid}"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    self._json({"ok": True, "message": f"Connecting to {ssid}…"})
                else:
                    self._json({"ok": False,
                                "error": result.stderr.strip() or result.stdout.strip()}, 500)
            else:
                self._json({"ok": False,
                            "error": "No supported WiFi backend found (nmcli / netsh)."}, 500)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)

    # ── API: POST /api/wifi/disconnect ────────────────────────────────
    def _api_wifi_disconnect(self) -> None:
        backend = self._wifi_backend()
        try:
            if backend == "nmcli":
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"],
                    text=True, timeout=8,
                )
                dev = next(
                    (l.split(":")[0] for l in out.splitlines()
                     if l.split(":")[1:2] == ["wifi"] and "connected" in l),
                    None,
                )
                if dev:
                    subprocess.run(["nmcli", "device", "disconnect", dev],
                                   check=True, timeout=15)
                    self._json({"ok": True, "message": f"Disconnected {dev}."})
                else:
                    self._json({"ok": True, "message": "No active WiFi connection."})
            elif backend == "netsh":
                subprocess.run(["netsh", "wlan", "disconnect"],
                               check=True, timeout=15)
                self._json({"ok": True, "message": "WiFi disconnected."})
            else:
                self._json({"ok": False,
                            "error": "No supported WiFi backend found."}, 500)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)

    # ── API: POST /api/download/start ─────────────────────────────────
    def _api_download_start(self, body: dict) -> None:
        url      = body.get("url", "").strip()
        dest_dir = body.get("dest_dir", "").strip() or str(Path.home() / "Downloads")
        filename = body.get("filename", "").strip()

        if not url:
            self._json({"error": "url is required"}, 400)
            return

        # Basic URL validation – must be http(s)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            self._json({"error": "Only http/https URLs are supported"}, 400)
            return

        # Derive filename from URL if not provided
        if not filename:
            filename = Path(parsed.path).name or "download.iso"
        # Sanitise: keep only safe characters
        filename = "".join(c for c in filename if c.isalnum() or c in "-_. ")
        if not filename:
            filename = "download.iso"

        dest_path = Path(dest_dir) / filename
        dl_id = str(uuid.uuid4())

        state: dict = {
            "id":        dl_id,
            "url":       url,
            "filename":  filename,
            "dest":      str(dest_path),
            "status":    "running",
            "downloaded": 0,
            "total":     0,
            "error":     None,
            "started":   time.time(),
        }
        with _downloads_lock:
            _downloads[dl_id] = state

        # Background thread
        def _run() -> None:
            try:
                Path(dest_dir).mkdir(parents=True, exist_ok=True)
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "nightmare-loader/downloader"},
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    total = int(resp.headers.get("Content-Length") or 0)
                    with _downloads_lock:
                        _downloads[dl_id]["total"] = total
                    chunk = 1 << 17  # 128 KiB
                    with open(dest_path, "wb") as fh:
                        while True:
                            with _downloads_lock:
                                if _downloads[dl_id]["status"] == "cancelled":
                                    return
                            data = resp.read(chunk)
                            if not data:
                                break
                            fh.write(data)
                            with _downloads_lock:
                                _downloads[dl_id]["downloaded"] += len(data)
                with _downloads_lock:
                    _downloads[dl_id]["status"] = "done"
            except Exception as exc:
                with _downloads_lock:
                    _downloads[dl_id]["status"] = "error"
                    _downloads[dl_id]["error"]  = str(exc)
                # Clean up partial file on error
                try:
                    dest_path.unlink(missing_ok=True)
                except OSError:
                    pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        self._json({"ok": True, "id": dl_id, "filename": filename, "dest": str(dest_path)})

    # ── API: GET /api/download/status?id=… ───────────────────────────
    def _api_download_status(self, dl_id: str) -> None:
        if not dl_id:
            # Return all downloads
            with _downloads_lock:
                self._json({"downloads": list(_downloads.values())})
            return
        with _downloads_lock:
            state = _downloads.get(dl_id)
        if state is None:
            self._json({"error": "Download ID not found"}, 404)
            return
        self._json(state)

    # ── API: POST /api/download/cancel ────────────────────────────────
    def _api_download_cancel(self, body: dict) -> None:
        dl_id = body.get("id", "").strip()
        if not dl_id:
            self._json({"error": "id is required"}, 400)
            return
        with _downloads_lock:
            state = _downloads.get(dl_id)
            if state is None:
                self._json({"error": "Download ID not found"}, 404)
                return
            if state["status"] == "running":
                state["status"] = "cancelled"
        self._json({"ok": True, "message": "Download cancelled."})

    # ── API: GET /api/update/check ────────────────────────────────────
    _GITHUB_API = "https://api.github.com/repos/NightmareDesigns/Nightmare-loader/releases/latest"

    def _api_update_check(self) -> None:
        from . import __version__
        try:
            req = urllib.request.Request(
                self._GITHUB_API,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": f"nightmare-loader/{__version__}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            latest_tag = data.get("tag_name", "").lstrip("v")
            html_url   = data.get("html_url", "")
            self._json({
                "current": __version__,
                "latest":  latest_tag,
                "url":     html_url,
                "up_to_date": latest_tag == __version__,
            })
        except Exception as exc:
            from . import __version__
            self._json({"current": __version__, "error": str(exc)}, 200)

    # ── API: POST /api/update/install ─────────────────────────────────
    _GITHUB_INSTALL_URL = (
        "git+https://github.com/NightmareDesigns/Nightmare-loader.git"
    )

    def _api_update_install(self) -> None:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade",
                 self._GITHUB_INSTALL_URL],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                self._json({"ok": True, "message": "Update installed. Restart nightmare-loader to apply."})
            else:
                self._json({"ok": False, "error": result.stderr.strip() or result.stdout.strip()}, 500)
        except subprocess.TimeoutExpired:
            self._json({"ok": False, "error": "Update timed out after 5 minutes."}, 500)
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
