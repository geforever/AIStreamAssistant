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
