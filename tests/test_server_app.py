from fastapi.testclient import TestClient

from g_chan.server.app import create_app
from g_chan.server.connection_manager import ConnectionManager


def test_health_endpoint_returns_ok_with_client_count():
    cm = ConnectionManager()
    app = create_app(cm, static_dir="non-existent-dir")
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["clients"] == 0


def test_ws_endpoint_accepts_connection_and_client_message_without_crash():
    """連上 WS → 發一條消息 → 關閉 — 全過程不應抛。"""
    cm = ConnectionManager()
    app = create_app(cm, static_dir="non-existent-dir")
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ready", "modelLoaded": True})
            # 不期望響應 — Phase 3a 只 log


def test_app_skips_static_mount_when_dir_missing():
    """static_dir 不存在 → 不挂 /,/ 路徑返回 404。"""
    cm = ConnectionManager()
    app = create_app(cm, static_dir="totally/does/not/exist")
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 404


def test_live2d_dir_serves_files(tmp_path):
    """live2d_dir 存在時 /live2d/<file> 應能 GET 到。"""
    cm = ConnectionManager()
    (tmp_path / "fake.model3.json").write_text('{"hello":"world"}', encoding="utf-8")
    app = create_app(cm, static_dir="missing", live2d_dir=str(tmp_path))
    with TestClient(app) as client:
        r = client.get("/live2d/fake.model3.json")
        assert r.status_code == 200
        assert r.json() == {"hello": "world"}


def test_live2d_dir_missing_no_crash():
    cm = ConnectionManager()
    app = create_app(cm, static_dir="missing", live2d_dir="totally/does/not/exist")
    with TestClient(app) as client:
        r = client.get("/live2d/anything")
        assert r.status_code == 404
