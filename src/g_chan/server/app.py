"""FastAPI app factory — /ws + /health + 可選 / (靜態 viewer 産物)。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from g_chan.server.connection_manager import ConnectionManager

log = logging.getLogger(__name__)


def create_app(
    connection_manager: ConnectionManager,
    *,
    static_dir: str | None = None,
    live2d_dir: str | None = None,
    init_payload: dict | None = None,
) -> FastAPI:
    """構造 FastAPI app。

    static_dir 不存在時:不挂 / 路徑,/ 會 404(正常,只服 /health + /ws)。
    live2d_dir 不存在時:不挂 /live2d,viewer 無法 fetch 模型資源。
    init_payload:WS 連接建立後立即發給該客戶端的初始化消息(viewer 用於同步 default 等配置)。
    """
    app = FastAPI(title="g_chan viewer server")

    @app.get("/health")
    async def health():
        return {"ok": True, "clients": connection_manager.client_count()}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await connection_manager.connect(websocket)
        if init_payload is not None:
            try:
                await websocket.send_json({"type": "init", **init_payload})
            except Exception as e:  # noqa: BLE001
                log.warning("ws init send failed: %s", e)
        try:
            while True:
                msg = await websocket.receive_json()
                log.debug("ws client → server: %r", msg)
        except WebSocketDisconnect:
            log.debug("ws client disconnected cleanly")
        except Exception as e:  # noqa: BLE001
            log.warning("ws endpoint loop error: %s", e)
        finally:
            connection_manager.disconnect(websocket)

    # /live2d/* — Live2D 模型資源;必須先於 / 注冊,因為 / 用 html=True 會貪婪匹配
    if live2d_dir and Path(live2d_dir).is_dir():
        app.mount("/live2d", StaticFiles(directory=live2d_dir), name="live2d")
        log.info("live2d assets mounted at /live2d from %s", live2d_dir)
    else:
        log.info("live2d_dir %r not found, /live2d not served", live2d_dir)

    # / — viewer 靜態産物
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="viewer")
        log.info("static viewer mounted at / from %s", static_dir)
    else:
        log.info("static_dir %r not found, /ws + /health only", static_dir)

    return app
