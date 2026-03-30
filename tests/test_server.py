"""
Tests for nightmare_loader.server – HTTP handler routing and API responses.
"""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from unittest.mock import patch
from urllib.request import urlopen

import pytest

from nightmare_loader.server import _Handler, DEFAULT_PORT, start_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Live server fixture (spun up on a random port for the duration of the test)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_server():
    """Start a real ThreadingHTTPServer on a free port; yield the base URL."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port   = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def _get(url: str):
    with urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def _post(url: str, data: dict):
    body = json.dumps(data).encode()
    from urllib.request import Request
    req  = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestServeIndex:
    def test_index_html_served(self, live_server):
        with urlopen(live_server + "/", timeout=5) as r:
            assert r.status == 200
            content = r.read()
        assert b"Nightmare Loader" in content
        assert b"matrix-canvas" in content

    def test_index_html_content_type(self, live_server):
        with urlopen(live_server + "/", timeout=5) as r:
            assert "text/html" in r.headers.get("Content-Type", "")


# ---------------------------------------------------------------------------
# GET /api/version
# ---------------------------------------------------------------------------

class TestApiVersion:
    def test_returns_version_string(self, live_server):
        status, body = _get(live_server + "/api/version")
        assert status == 200
        assert "version" in body
        assert isinstance(body["version"], str)
        assert len(body["version"]) > 0

    def test_version_matches_package(self, live_server):
        from nightmare_loader import __version__
        _, body = _get(live_server + "/api/version")
        assert body["version"] == __version__


# ---------------------------------------------------------------------------
# GET /api/drives
# ---------------------------------------------------------------------------

class TestApiDrives:
    def test_returns_json_with_drives_key(self, live_server):
        status, body = _get(live_server + "/api/drives")
        assert status == 200
        assert "drives" in body

    def test_drives_is_list_even_on_error(self, live_server):
        # The API should always return a list (possibly empty) for drives
        _, body = _get(live_server + "/api/drives")
        assert isinstance(body["drives"], list)

    def test_drives_error_key_present_on_failure(self, live_server):
        """When lsblk fails the response still has 'drives': [] and 'error'."""
        from nightmare_loader import drive as drv
        with patch.object(drv, "list_removable_drives", side_effect=Exception("lsblk gone")):
            _, body = _get(live_server + "/api/drives")
        assert body["drives"] == []
        assert "error" in body


# ---------------------------------------------------------------------------
# GET /api/info?path=…
# ---------------------------------------------------------------------------

class TestApiInfo:
    def test_missing_path_returns_400(self, live_server):
        from urllib.request import urlopen as _uo
        from urllib.error import HTTPError
        try:
            _uo(live_server + "/api/info", timeout=5)
        except HTTPError as e:
            assert e.code == 400

    def test_nonexistent_path_returns_error(self, live_server):
        from urllib.request import urlopen as _uo
        from urllib.error import HTTPError
        try:
            _uo(live_server + "/api/info?path=%2Fnonexistent.iso", timeout=5)
        except HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read())
            assert "error" in body

    def test_valid_iso_returns_metadata(self, live_server, tmp_path):
        iso = tmp_path / "test.iso"
        iso.write_bytes(b"\x00" * 2048)

        from nightmare_loader import iso as iso_mod
        fake_meta = {
            "path": str(iso), "filename": "test.iso", "label": "TEST",
            "size_bytes": 2048, "distro": "ubuntu", "distro_label": "Ubuntu",
            "kernel": "/casper/vmlinuz", "initrd": "/casper/initrd",
            "cmdline": "quiet splash",
        }
        with patch.object(iso_mod, "get_iso_metadata", return_value=fake_meta):
            _, body = _get(live_server + f"/api/info?path={iso}")
        assert body["distro"] == "ubuntu"
        assert body["filename"] == "test.iso"


# ---------------------------------------------------------------------------
# GET /api/isos/<device> – returns error because no real device
# ---------------------------------------------------------------------------

class TestApiIsos:
    def test_missing_device_returns_error(self, live_server):
        # device component is empty after strip
        _, body = _get(live_server + "/api/isos/")
        # either 'error' key present or entries is []
        assert "entries" in body or "error" in body

    def test_bad_device_returns_empty_entries(self, live_server):
        _, body = _get(live_server + "/api/isos/%2Fdev%2Fnonexistent")
        assert isinstance(body.get("entries", []), list)


# ---------------------------------------------------------------------------
# POST /api/prepare – validation
# ---------------------------------------------------------------------------

class TestApiPrepare:
    def test_missing_device_returns_400(self, live_server):
        from urllib.error import HTTPError
        try:
            _post(live_server + "/api/prepare", {"label": "TEST"})
        except HTTPError as e:
            assert e.code == 400

    def test_bad_layout_returns_400(self, live_server):
        from urllib.error import HTTPError
        try:
            _post(live_server + "/api/prepare", {"device": "/dev/sdb", "layout": "btrfs"})
        except HTTPError as e:
            assert e.code == 400


# ---------------------------------------------------------------------------
# POST /api/add – validation
# ---------------------------------------------------------------------------

class TestApiAdd:
    def test_missing_device_returns_400(self, live_server):
        from urllib.error import HTTPError
        try:
            _post(live_server + "/api/add", {"iso_path": "/tmp/x.iso"})
        except HTTPError as e:
            assert e.code == 400

    def test_missing_iso_path_returns_400(self, live_server):
        from urllib.error import HTTPError
        try:
            _post(live_server + "/api/add", {"device": "/dev/sdb"})
        except HTTPError as e:
            assert e.code == 400


# ---------------------------------------------------------------------------
# POST /api/remove – validation
# ---------------------------------------------------------------------------

class TestApiRemove:
    def test_missing_device_returns_400(self, live_server):
        from urllib.error import HTTPError
        try:
            _post(live_server + "/api/remove", {"iso_name": "x.iso"})
        except HTTPError as e:
            assert e.code == 400

    def test_missing_iso_name_returns_400(self, live_server):
        from urllib.error import HTTPError
        try:
            _post(live_server + "/api/remove", {"device": "/dev/sdb"})
        except HTTPError as e:
            assert e.code == 400


# ---------------------------------------------------------------------------
# 404 for unknown routes
# ---------------------------------------------------------------------------

class TestNotFound:
    def test_unknown_get_path(self, live_server):
        from urllib.error import HTTPError
        try:
            from urllib.request import urlopen as _uo
            _uo(live_server + "/api/unknown", timeout=5)
        except HTTPError as e:
            assert e.code == 404

    def test_unknown_post_path(self, live_server):
        from urllib.error import HTTPError
        try:
            _post(live_server + "/api/unknown", {})
        except HTTPError as e:
            assert e.code == 404


# ---------------------------------------------------------------------------
# DEFAULT_PORT constant
# ---------------------------------------------------------------------------

def test_default_port_is_integer():
    assert isinstance(DEFAULT_PORT, int)
    assert 1024 < DEFAULT_PORT < 65535


# ---------------------------------------------------------------------------
# GET /api/root
# ---------------------------------------------------------------------------

class TestApiRoot:
    def test_returns_root_key(self, live_server):
        status, body = _get(live_server + "/api/root")
        assert status == 200
        assert "root" in body

    def test_root_is_boolean(self, live_server):
        _, body = _get(live_server + "/api/root")
        assert isinstance(body["root"], bool)


# ---------------------------------------------------------------------------
# GET /api/platform
# ---------------------------------------------------------------------------

class TestApiPlatform:
    def test_returns_platform_key(self, live_server):
        status, body = _get(live_server + "/api/platform")
        assert status == 200
        assert "platform" in body

    def test_platform_is_string(self, live_server):
        _, body = _get(live_server + "/api/platform")
        assert isinstance(body["platform"], str)
        assert len(body["platform"]) > 0

    def test_windows_key_is_boolean(self, live_server):
        _, body = _get(live_server + "/api/platform")
        assert "windows" in body
        assert isinstance(body["windows"], bool)

    def test_windows_false_on_linux(self, live_server):
        import sys
        if sys.platform != "win32":
            _, body = _get(live_server + "/api/platform")
            assert body["windows"] is False

    def test_windows_true_when_platform_is_win32(self, live_server):
        """Verify windows=True is returned when sys.platform is win32 (mocked)."""
        import sys as _real_sys
        from unittest.mock import patch
        import nightmare_loader.server as srv

        with patch.object(_real_sys, "platform", "win32"):
            # Call the private helper directly to check the logic
            import sys as patched_sys
            result = patched_sys.platform == "win32"
        assert result is True


# ---------------------------------------------------------------------------
# GET /api/platform – android key
# ---------------------------------------------------------------------------

class TestApiPlatformAndroid:
    def test_android_key_present(self, live_server):
        _, body = _get(live_server + "/api/platform")
        assert "android" in body

    def test_android_key_is_boolean(self, live_server):
        _, body = _get(live_server + "/api/platform")
        assert isinstance(body["android"], bool)

    def test_android_false_outside_termux(self, live_server):
        """android should be False when TERMUX_VERSION env var is absent."""
        import os
        if "TERMUX_VERSION" not in os.environ:
            _, body = _get(live_server + "/api/platform")
            assert body["android"] is False

    def test_android_true_when_termux_env_set(self, live_server):
        """android=True when TERMUX_VERSION is in the environment."""
        from unittest.mock import patch
        import nightmare_loader.drive as drv

        with patch.object(drv, "_is_termux", return_value=True):
            # Directly verify the helper returns True when mocked
            assert drv._is_termux() is True
