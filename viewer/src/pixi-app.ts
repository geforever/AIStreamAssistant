import * as PIXI from "pixi.js";

import type { ViewerConfig } from "./config";

/** 创建 PixiJS Application,backgroundAlpha / backgroundColor 由 ViewerConfig 决定。
 *
 * 复用 index.html 里已有的 #stage canvas,避免 PixiJS 自己创建一个浮动 canvas
 * 干扰 OBS browser source 抓屏。
 */
export function createPixiApp(cfg: ViewerConfig): PIXI.Application {
  const canvas = document.getElementById("stage") as HTMLCanvasElement | null;
  if (!canvas) {
    throw new Error("missing <canvas id='stage'> in index.html");
  }

  const app = new PIXI.Application({
    view: canvas,
    width: window.innerWidth,
    height: window.innerHeight,
    backgroundColor: cfg.backgroundColor ?? 0x000000,
    backgroundAlpha: cfg.backgroundAlpha,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  });

  window.addEventListener("resize", () => {
    app.renderer.resize(window.innerWidth, window.innerHeight);
  });

  return app;
}
