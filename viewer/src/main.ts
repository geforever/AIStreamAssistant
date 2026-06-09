import { readConfig } from "./config";
import { Live2DController } from "./live2d";
import { createPixiApp } from "./pixi-app";
import type { ServerMessage } from "./types";
import { WSClient } from "./ws";

const WS_URL = `ws://${window.location.host}/ws`;

async function main() {
  console.log("g-chan viewer boot");

  const cfg = readConfig();
  const app = createPixiApp(cfg);
  const live2d = new Live2DController();
  await live2d.load(app, cfg.modelUrl);
  console.log("live2d ready, model:", cfg.modelUrl);

  // Chrome 严格 autoplay policy:AudioContext.resume() + audio.play() 都需用户手势
  // 默认显示"点击开始"遮罩,点完才解锁 audio 并移除遮罩。
  // OBS browser source 用 ?nooverlay=1 跳过(OBS 默认允许 autoplay,会自动 resume)
  const params = new URLSearchParams(window.location.search);
  if (params.get("nooverlay") === "1") {
    void live2d.unlockAudio();
  } else {
    _showUnlockOverlay(() => void live2d.unlockAudio());
  }

  const ws = new WSClient(WS_URL, async (msg: ServerMessage) => {
    switch (msg.type) {
      case "init":
        console.log("← init", msg);
        live2d.setDefaults(msg.default_expression, msg.expression_revert_ms);
        break;
      case "expression":
        console.log("← expression", msg.name);
        live2d.applyExpression(msg.name);
        break;
      case "motion":
        console.log("← motion", msg.name);
        live2d.applyMotion(msg.name);
        break;
      case "speak":
        console.log("← speak:", msg.text);
        await live2d.speak(msg.audio, msg.format);
        break;
      case "ping":
        break;
    }
  });
  ws.connect();

  const dbg = window as unknown as { live2d: Live2DController; ws: WSClient };
  dbg.live2d = live2d;
  dbg.ws = ws;
}

main().catch((e) => console.error("viewer boot failed:", e));

function _showUnlockOverlay(onClick: () => void): void {
  const overlay = document.createElement("div");
  overlay.id = "unlock-overlay";
  overlay.textContent = "点击开启 G 酱 (click to start)";
  overlay.style.cssText = `
    position: fixed; inset: 0; z-index: 9999;
    display: flex; align-items: center; justify-content: center;
    background: rgba(0, 0, 0, 0.55); color: white;
    font: 600 22px / 1.4 system-ui, -apple-system, sans-serif;
    cursor: pointer; user-select: none;
  `;
  overlay.addEventListener("click", () => {
    onClick();
    overlay.remove();
  }, { once: true });
  document.body.appendChild(overlay);
}
