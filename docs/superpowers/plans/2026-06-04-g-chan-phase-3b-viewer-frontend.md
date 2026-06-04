# G 酱 — Phase 3b Implementation Plan(viewer 前端)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 浏览器端 viewer — Vite + TypeScript + PixiJS + pixi-live2d-display,从 `/ws` 接收 Phase 3a 推的 `expression` / `motion` / `speak` 消息,实时驱动 Live2D 角色 + 音量驱动 lipsync,透明背景方便 OBS browser source 直接叠加。

**Architecture:** 
- 静态:viewer 是纯前端单页,build 产物 `viewer/dist/` 通过 FastAPI `StaticFiles` 挂载在 `/`(Phase 3a 已写好)
- 模型:Live2D 资源(model3.json + textures + motions)由后端额外挂在 `/live2d/`(Phase 3a 的 `create_app` 需要扩展)
- 运行时:浏览器进 `http://localhost:8765/` → 加载 pixi 应用 → fetch `/live2d/<model_path>` → 连 `ws://localhost:8765/ws` → 收消息驱动模型
- Cubism Core(Live2D 专有 runtime js)需要用户手动下载放进 `viewer/public/cubismcore/`(license 限制)

**Tech Stack:**
- Build:Vite 5 + TypeScript 5
- 渲染:PixiJS 7.x
- Live2D:pixi-live2d-display ^0.4(支持 Cubism 4 + 内置 lipsync 通过 `model.speak()`)
- 包管理器:`npm`(viewer 是独立子项目,跟 `uv` 后端互不影响)

**用户偏好:**
- 此项目不提交 git,所有 task 跳过 commit 步骤
- 后端约定 lowercase(expression/motion/语言全小写),viewer 直接转发即可不再做大小写处理

**Phase 3b 不做:**
- 自动测试(viewer 是视觉产物,集成验证靠人眼;Vitest/Playwright 等待 Phase 4)
- 多 model 切换 UI(单 model,model_path 由后端配置决定)
- 表情/动作选择器 UI(运行时全自动,LLM 驱动)
- HTTPS / 远程部署优化

---

## 文件结构(新增)

```
viewer/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  public/
    cubismcore/
      live2dcubismcore.min.js   ← 用户从 Live2D 官网下载放进来
    .gitignore                  ← 忽略 cubismcore 内容(license)
  src/
    main.ts          # 入口:bootstrap pixi + live2d + ws
    pixi-app.ts      # PixiJS Application + 透明背景 + resize 处理
    live2d.ts        # Live2DController:加载模型 + apply expression/motion/speak
    ws.ts            # WSClient:连接 + 自动重连 + 消息分发
    types.ts         # ServerMessage discriminated union(对应 Phase 3a 协议)
    config.ts        # URL 参数解析(?bg=color, ?model=path 覆盖默认)
```

## 后端改动

- `src/g_chan/server/app.py` 的 `create_app(...)` 增加 `live2d_dir: str | None` 参数,有效目录时挂载在 `/live2d/`
- `src/g_chan/__main__.py` 计算 Live2D 根目录后传给 `create_app`

---

## Task 1: 用户手动准备 Cubism Core

**这一步只能用户做,不能 agent 自动化(Live2D 官网下载需登录 + 接受 EULA)。**

- [ ] 用户访问 https://www.live2d.com/en/sdk/download/web/
- [ ] 下载 Cubism SDK for Web(任意最新版,目前 5.x)
- [ ] 解压后从 `Core/live2dcubismcore.min.js` 取出 *只这一个文件*
- [ ] 后续 Task 2 会指定放进 `viewer/public/cubismcore/live2dcubismcore.min.js`

**为什么这步必须人工:** pixi-live2d-display 不打包 Cubism Core,需用户接受 Live2D EULA 后单独获取。一旦放好,后续 Task 全自动。

## Report

- **Status:** DONE | BLOCKED
- 若 BLOCKED:可暂时 stub 这个 js 内容("一行 console.warn"),其余流程能继续,只是模型渲染要等真文件到位

---

## Task 2: Viewer scaffolding(Vite + TS + 依赖)

**Files:**
- Create: `viewer/package.json`
- Create: `viewer/vite.config.ts`
- Create: `viewer/tsconfig.json`
- Create: `viewer/index.html`
- Create: `viewer/public/.gitignore`
- Create: `viewer/public/cubismcore/.gitkeep`
- Create: `viewer/src/main.ts`(占位,只 console.log)

### Step 2.1: 项目根 `mkdir`

```bash
cd /Users/geforever/Desktop/Gちゃん
mkdir -p viewer/src viewer/public/cubismcore
```

### Step 2.2: `viewer/package.json`

```json
{
  "name": "g-chan-viewer",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "pixi-live2d-display": "^0.4.0",
    "pixi.js": "^7.4.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "vite": "^5.2.0"
  }
}
```

### Step 2.3: `viewer/vite.config.ts`

```ts
import { defineConfig } from "vite";

export default defineConfig({
  // build 产物输出到 viewer/dist,Phase 3a 后端默认从这里挂载
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2020",
  },
  server: {
    port: 5173,
    // 开发模式 vite dev server 时,WS / live2d 都代理到后端 8765
    proxy: {
      "/ws":      { target: "ws://localhost:8765", ws: true },
      "/live2d":  { target: "http://localhost:8765", changeOrigin: true },
    },
  },
});
```

### Step 2.4: `viewer/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "useDefineForClassFields": true,
    "allowSyntheticDefaultImports": true,
    "resolveJsonModule": true,
    "types": []
  },
  "include": ["src/**/*.ts"]
}
```

### Step 2.5: `viewer/index.html`

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>G 酱 viewer</title>
    <!-- Live2D Cubism Core(用户手动放好,license 限制不打包) -->
    <script src="/cubismcore/live2dcubismcore.min.js"></script>
    <style>
      html, body {
        margin: 0; padding: 0;
        width: 100%; height: 100%;
        overflow: hidden;
        background: transparent;
      }
      #stage {
        position: fixed; inset: 0;
      }
    </style>
  </head>
  <body>
    <canvas id="stage"></canvas>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

### Step 2.6: `viewer/public/.gitignore`

```
# Cubism Core is downloaded per-developer (license requires accepting EULA)
cubismcore/*
!cubismcore/.gitkeep
```

### Step 2.7: `viewer/public/cubismcore/.gitkeep`

空文件(`touch viewer/public/cubismcore/.gitkeep`)

### Step 2.8: `viewer/src/main.ts`(占位)

```ts
console.log("g-chan viewer boot — Phase 3b scaffold");
```

### Step 2.9: 安装依赖

```bash
cd viewer && npm install 2>&1 | tail -5
```

Expect:`added N packages, ...` 无 error。可能有 warning(peer deps、deprecated),忽略即可。

### Step 2.10: 验证 build 产物

```bash
cd viewer && npm run build 2>&1 | tail -10
```

Expect:`✓ built in ...`,生成 `viewer/dist/index.html` + `viewer/dist/assets/main-<hash>.js`。

```bash
ls viewer/dist/
```

Expect: `assets/  cubismcore/  index.html`(public/ 内容会被复制到 dist/ 根)。

## Self-Review

- [ ] viewer/ 目录树正确
- [ ] `npm install` 无致命错误
- [ ] `npm run build` 产生 viewer/dist/
- [ ] viewer/dist/index.html 引用 `/cubismcore/live2dcubismcore.min.js`(无论实际 js 是否到位)
- [ ] tsconfig strict + noUnusedLocals + noUnusedParameters 开启
- [ ] 没有 git commits

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 安装的 pixi.js 和 pixi-live2d-display 实际版本号
- 任何 npm warning 中需要关注的

---

## Task 3: 后端扩展 — `/live2d/` 静态挂载

**Files:**
- Modify: `src/g_chan/server/app.py`
- Modify: `src/g_chan/__main__.py`
- Modify: `tests/test_server_app.py`(+ 1 test)

### Step 3.1: 修改 `src/g_chan/server/app.py`

`create_app` 函数签名加 `live2d_dir: str | None = None` 参数(放在 `static_dir` 之后)。在挂载 `/` 静态文件之前 *先* 挂载 `/live2d` —— 因为 `/` 用 `html=True`,会接管所有未匹配路径,必须在它之前注册 `/live2d`:

```python
def create_app(
    connection_manager: ConnectionManager,
    *,
    static_dir: str | None = None,
    live2d_dir: str | None = None,
) -> FastAPI:
    app = FastAPI(title="g_chan viewer server")

    @app.get("/health")
    async def health():
        return {"ok": True, "clients": connection_manager.client_count()}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await connection_manager.connect(websocket)
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

    # /live2d/* — Live2D 模型资源(model3.json + textures + motions)
    # 必须在 / 静态挂载之前注册,否则 html=True 会优先匹配
    if live2d_dir and Path(live2d_dir).is_dir():
        app.mount("/live2d", StaticFiles(directory=live2d_dir), name="live2d")
        log.info("live2d assets mounted at /live2d from %s", live2d_dir)
    else:
        log.info("live2d_dir %r not found, /live2d not served", live2d_dir)

    # / — viewer 静态产物
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="viewer")
        log.info("static viewer mounted at / from %s", static_dir)
    else:
        log.info("static_dir %r not found, /ws + /health only", static_dir)

    return app
```

### Step 3.2: 添加测试 `tests/test_server_app.py`(追加到末尾)

```python
def test_live2d_dir_serves_files(tmp_path):
    """live2d_dir 存在时 /live2d/<file> 应能 GET 到。"""
    cm = ConnectionManager()
    # 造一个假资源文件
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
```

### Step 3.3: 跑测试,确认绿

```bash
uv run pytest tests/test_server_app.py -v 2>&1 | tail -10
```

Expect:5 个 test 全 pass(3 个旧 + 2 个新)。

### Step 3.4: 修改 `src/g_chan/__main__.py`

`create_app` 调用处加 `live2d_dir`。考虑 cfg.live2d.enabled 和 model_path 的语义:

- 有 model 时:`live2d_dir = Path(live2d_model.path).parent` 不够,因为模型可能引用上级目录的 texture(实际上 model3.json 引用都是相对自身的 `Live2D/Epsilon_free/runtime/textures/...`)。安全做法是挂 `Live2D/` 根目录,viewer 用相对 model_path 来 fetch
- 没 model 时:不挂

具体策略:挂载 `Live2D/` 根目录(项目 cwd 下),viewer 通过 `?model=<relative-path-from-Live2D-root>` 访问。

替换 __main__.py 里 `app = create_app(conn_manager, static_dir=cfg.server.static_dir)` 那一行为:

```python
        live2d_root = "Live2D" if live2d_model is not None else None
        app = create_app(
            conn_manager,
            static_dir=cfg.server.static_dir,
            live2d_dir=live2d_root,
        )
```

### Step 3.5: 全套测试 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```

Expect:`132 passed`(130 + 2 new),ruff clean。

## Self-Review

- [ ] `create_app` 接 `live2d_dir`,有效时挂在 `/live2d`
- [ ] `/live2d` 挂载顺序在 `/` 之前
- [ ] 2 个新测试 pass
- [ ] `__main__.py` 调用处加 `live2d_dir`
- [ ] 132 passed, ruff clean
- [ ] 没有 git commits

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 4: PixiJS app + 透明 canvas + resize

**Files:**
- Create: `viewer/src/pixi-app.ts`
- Modify: `viewer/src/main.ts`

### Step 4.1: 写 `viewer/src/pixi-app.ts`

```ts
import * as PIXI from "pixi.js";

/** 创建一个透明背景、全屏跟随 window resize 的 PixiJS Application。
 *
 * canvas 通过 id #stage 复用 — 在 index.html 已存在,避免 PixiJS 自己创建一个浮动 canvas
 * 干扰 OBS 截屏。
 */
export function createPixiApp(): PIXI.Application {
  const canvas = document.getElementById("stage") as HTMLCanvasElement | null;
  if (!canvas) {
    throw new Error("missing <canvas id='stage'> in index.html");
  }

  const app = new PIXI.Application({
    view: canvas,
    width: window.innerWidth,
    height: window.innerHeight,
    backgroundAlpha: 0,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  });

  window.addEventListener("resize", () => {
    app.renderer.resize(window.innerWidth, window.innerHeight);
  });

  return app;
}
```

### Step 4.2: 修改 `viewer/src/main.ts`

```ts
import { createPixiApp } from "./pixi-app";

async function main() {
  console.log("g-chan viewer boot");
  const app = createPixiApp();
  console.log("pixi ready", app.renderer.width, app.renderer.height);
}

main().catch((e) => console.error("viewer boot failed:", e));
```

### Step 4.3: 验证 dev 启动

```bash
cd viewer && timeout 5 npm run dev 2>&1 | head -10 || true
```

Expect:Vite 输出 `Local: http://localhost:5173/`,无 TS 错误。

### Step 4.4: 验证 build

```bash
cd viewer && npm run build 2>&1 | tail -5
```

Expect:`✓ built in ...`。

## Self-Review

- [ ] pixi-app.ts 用现成 #stage canvas(不新建 DOM)
- [ ] `backgroundAlpha: 0` → 透明
- [ ] resize 监听器到位
- [ ] main.ts 引用 createPixiApp 并 log
- [ ] vite build 通过

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 5: Live2DController — 加载模型 + 暴露 expression/motion/speak

**Files:**
- Create: `viewer/src/live2d.ts`
- Modify: `viewer/src/main.ts`

注:pixi-live2d-display 的 `Live2DModel.from()` 返回的 PIXI.DisplayObject 自带 `expression(name)` / `motion(group)` / `speak({src})` 方法。Idle eyeblink + breath 在模型 model3.json 有相应参数时自动启用。

### Step 5.1: 写 `viewer/src/live2d.ts`

```ts
import * as PIXI from "pixi.js";
import { Live2DModel } from "pixi-live2d-display/cubism4";

// 把 PIXI 暴露给 pixi-live2d-display 内部使用
// (它默认不知道 PIXI 在哪儿,需要全局注入)
(window as unknown as { PIXI: typeof PIXI }).PIXI = PIXI;

export class Live2DController {
  private model: Live2DModel | null = null;

  /** 加载模型并居中铺到 canvas 上。
   * modelUrl:相对 /live2d 挂载根目录的路径,例如 "/live2d/Epsilon_free/runtime/Epsilon_free.model3.json"
   */
  async load(app: PIXI.Application, modelUrl: string): Promise<void> {
    const model = await Live2DModel.from(modelUrl);
    this.model = model;

    // 居中 + 等比缩放到画布高 80%
    this._fit(app);
    window.addEventListener("resize", () => this._fit(app));

    app.stage.addChild(model);
  }

  private _fit(app: PIXI.Application): void {
    if (!this.model) return;
    const m = this.model;
    const targetH = app.renderer.height * 0.95;
    const scale = targetH / m.height;
    m.scale.set(scale);
    m.x = (app.renderer.width - m.width) / 2;
    m.y = (app.renderer.height - m.height) / 2;
  }

  /** name 为模型 model3.json 中定义的 expression name(小写约定由后端保证)。
   * 不存在的名字 pixi-live2d-display 内部 warn 并 noop。
   * "none" 视为不切换 — 保持当前表情。
   */
  applyExpression(name: string): void {
    if (!this.model || !name || name === "none") return;
    this.model.expression(name);
  }

  /** group 为 motion group 名(model3.json FileReferences.Motions key,小写约定)。
   * pixi-live2d-display 会从 group 内随机挑一个 motion 播放。
   * "none" 视为不触发动作。
   */
  applyMotion(group: string): void {
    if (!this.model || !group || group === "none") return;
    this.model.motion(group);
  }

  /** 播放 base64 编码的 mp3 + 自动 lipsync(基于音量驱动 ParamMouthOpenY)。 */
  async speak(base64Audio: string, format: string): Promise<void> {
    if (!this.model) return;
    const url = `data:audio/${format};base64,${base64Audio}`;
    // pixi-live2d-display speak() 自动接管 lipsync,音频播放完恢复闭嘴
    await this.model.speak(url, {
      volume: 1.0,
      crossOrigin: "anonymous",
    });
  }
}
```

### Step 5.2: 修改 `viewer/src/main.ts`

```ts
import { Live2DController } from "./live2d";
import { createPixiApp } from "./pixi-app";

const DEFAULT_MODEL_URL = "/live2d/Epsilon_free/runtime/Epsilon_free.model3.json";

async function main() {
  console.log("g-chan viewer boot");
  const app = createPixiApp();

  const live2d = new Live2DController();
  await live2d.load(app, DEFAULT_MODEL_URL);
  console.log("live2d ready");

  // 临时:暴露到 window 方便浏览器 console 手动测试
  (window as unknown as { live2d: Live2DController }).live2d = live2d;
}

main().catch((e) => console.error("viewer boot failed:", e));
```

### Step 5.3: 验证 build

```bash
cd viewer && npm run build 2>&1 | tail -5
```

Expect:`✓ built in ...`。pixi-live2d-display 在 cubism4 子路径下,TypeScript 应能解析。如果报 `Cannot find module 'pixi-live2d-display/cubism4'`,看 Concerns 部分。

### Step 5.4: 手动验证(用户)

提示用户:

> 启动后端 `uv run python -m g_chan`(确保 config.yaml 有 server 块)。
> Live2D Cubism Core 必须已经放进 `viewer/public/cubismcore/live2dcubismcore.min.js`。
> 重新 `cd viewer && npm run build`,然后浏览器打开 `http://localhost:8765/`。
> 应能看到 G 酱模型在透明背景上居中显示,自动眨眼 + 呼吸。
> 浏览器 console 输入 `window.live2d.applyExpression('smile')` 测试表情切换。
> 输入 `window.live2d.applyMotion('tap')` 测试动作。

## Self-Review

- [ ] Live2DController 4 个方法(load / applyExpression / applyMotion / speak)
- [ ] "none" 在 expression/motion 视为 noop
- [ ] _fit 在 resize 时自动重算
- [ ] pixi-live2d-display 的 cubism4 子模块正确 import
- [ ] window.PIXI 注入到位
- [ ] vite build 通过
- [ ] main.ts 临时挂 window.live2d 方便手动测试

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 用户手动验证结果(若 agent 跑此 task)或留给下游 Task 9 验证

### Concerns 可能项

- 如 `pixi-live2d-display/cubism4` 路径无法解析:可能 v0.4 包结构不同,改成 `import { Live2DModel } from "pixi-live2d-display"` 并加 `"types": ["pixi-live2d-display"]` 到 tsconfig
- `Live2DModel.from()` 期望同源,模型 fetch 若 CORS 失败:确认 vite proxy `/live2d` 转发到后端

---

## Task 6: WSClient — 连接 + 自动重连

**Files:**
- Create: `viewer/src/types.ts`
- Create: `viewer/src/ws.ts`

### Step 6.1: 写 `viewer/src/types.ts`

```ts
/** Phase 3a 后端 → 前端协议(必须跟 src/g_chan/viewer_sink/ws_sink.py 保持一致)。 */
export type ServerMessage =
  | { type: "expression"; name: string }
  | { type: "motion"; name: string }
  | { type: "speak"; audio: string; format: string; text: string }
  | { type: "ping" };
```

### Step 6.2: 写 `viewer/src/ws.ts`

```ts
import type { ServerMessage } from "./types";

type Handler = (msg: ServerMessage) => void | Promise<void>;

/** WebSocket 客户端 — 自动重连(指数退避),透明消息分发。
 *
 * 重连策略:首次失败 1s 后试,每次 ×2 上限 30s。
 * 连上后退避归零。
 */
export class WSClient {
  private ws: WebSocket | null = null;
  private backoffMs = 1000;
  private maxBackoffMs = 30_000;
  private closedByUser = false;

  constructor(private url: string, private onMessage: Handler) {}

  connect(): void {
    this.closedByUser = false;
    this._open();
  }

  close(): void {
    this.closedByUser = true;
    this.ws?.close();
  }

  private _open(): void {
    console.log("ws connecting:", this.url);
    this.ws = new WebSocket(this.url);

    this.ws.addEventListener("open", () => {
      console.log("ws open");
      this.backoffMs = 1000;
    });

    this.ws.addEventListener("message", (ev) => {
      try {
        const msg = JSON.parse(ev.data) as ServerMessage;
        void this.onMessage(msg);
      } catch (e) {
        console.warn("ws bad message:", e, ev.data);
      }
    });

    this.ws.addEventListener("close", () => {
      console.log("ws closed");
      this.ws = null;
      if (!this.closedByUser) this._scheduleReconnect();
    });

    this.ws.addEventListener("error", (e) => {
      console.warn("ws error:", e);
      // close 事件会跟着触发,统一在 close 里 schedule
    });
  }

  private _scheduleReconnect(): void {
    const delay = this.backoffMs;
    this.backoffMs = Math.min(this.backoffMs * 2, this.maxBackoffMs);
    console.log(`ws reconnect in ${delay}ms`);
    setTimeout(() => {
      if (!this.closedByUser) this._open();
    }, delay);
  }
}
```

### Step 6.3: 验证 build

```bash
cd viewer && npm run build 2>&1 | tail -5
```

Expect:`✓ built`。

## Self-Review

- [ ] ServerMessage type 匹配后端 protocol
- [ ] WSClient 自动重连指数退避
- [ ] 错误日志清晰
- [ ] vite build 通过

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 7: 消息分发 — WS → Live2DController

**Files:**
- Modify: `viewer/src/main.ts`

### Step 7.1: 替换 `viewer/src/main.ts` 完整内容

```ts
import { Live2DController } from "./live2d";
import { createPixiApp } from "./pixi-app";
import type { ServerMessage } from "./types";
import { WSClient } from "./ws";

const DEFAULT_MODEL_URL = "/live2d/Epsilon_free/runtime/Epsilon_free.model3.json";
const WS_URL = `ws://${window.location.host}/ws`;

async function main() {
  console.log("g-chan viewer boot");

  const app = createPixiApp();
  const live2d = new Live2DController();
  await live2d.load(app, DEFAULT_MODEL_URL);
  console.log("live2d ready");

  const ws = new WSClient(WS_URL, async (msg: ServerMessage) => {
    switch (msg.type) {
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
        // 仅维持连接,不响应
        break;
    }
  });
  ws.connect();

  // 调试入口
  (window as unknown as { live2d: Live2DController; ws: WSClient }).live2d = live2d;
  (window as unknown as { live2d: Live2DController; ws: WSClient }).ws = ws;
}

main().catch((e) => console.error("viewer boot failed:", e));
```

### Step 7.2: 验证 build

```bash
cd viewer && npm run build 2>&1 | tail -5
```

Expect:`✓ built`。

## Self-Review

- [ ] 4 个 message type 全部 case
- [ ] discriminated union 的 switch 满足 TS 穷尽性
- [ ] WSClient 实例 connect
- [ ] vite build 通过

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 8: URL 参数 — ?bg=color 开发用 + ?model=path 覆盖默认

**Files:**
- Create: `viewer/src/config.ts`
- Modify: `viewer/src/main.ts`
- Modify: `viewer/src/pixi-app.ts`(接受 backgroundAlpha override)

### Step 8.1: 写 `viewer/src/config.ts`

```ts
/** 浏览器 URL 参数解析。
 *
 * ?bg=#222 / ?bg=rgba(0,0,0,0.5) → 开发时给个可见底色方便调试,默认透明
 * ?model=/live2d/Other/Other.model3.json → 覆盖默认模型
 */
export interface ViewerConfig {
  backgroundColor: number | null;   // null = 透明
  backgroundAlpha: number;          // 0 = 透明
  modelUrl: string;
}

const DEFAULT_MODEL_URL = "/live2d/Epsilon_free/runtime/Epsilon_free.model3.json";

export function readConfig(): ViewerConfig {
  const params = new URLSearchParams(window.location.search);

  const bg = params.get("bg");
  let backgroundColor: number | null = null;
  let backgroundAlpha = 0;
  if (bg) {
    const parsed = _parseColor(bg);
    if (parsed !== null) {
      backgroundColor = parsed;
      backgroundAlpha = 1;
    }
  }

  return {
    backgroundColor,
    backgroundAlpha,
    modelUrl: params.get("model") ?? DEFAULT_MODEL_URL,
  };
}

function _parseColor(s: string): number | null {
  // 仅支持 #rrggbb / #rgb,够开发用
  const m = s.match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (!m) return null;
  let hex = m[1];
  if (hex.length === 3) {
    hex = hex.split("").map((c) => c + c).join("");
  }
  return parseInt(hex, 16);
}
```

### Step 8.2: 修改 `viewer/src/pixi-app.ts`,接受 config

```ts
import * as PIXI from "pixi.js";

import type { ViewerConfig } from "./config";

export function createPixiApp(cfg: ViewerConfig): PIXI.Application {
  const canvas = document.getElementById("stage") as HTMLCanvasElement | null;
  if (!canvas) {
    throw new Error("missing <canvas id='stage'> in index.html");
  }

  const app = new PIXI.Application({
    view: canvas,
    width: window.innerWidth,
    height: window.innerHeight,
    background: cfg.backgroundColor ?? undefined,
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
```

### Step 8.3: 修改 `viewer/src/main.ts` 使用 config

替换开头的 `import` 和 `main` 前 N 行:

```ts
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

  // ... 下面 WSClient + switch 等保持不变
```

(下面的 WSClient 实例化和 switch case 部分不动,只是开头变成读 config + 把 cfg.modelUrl 传给 live2d.load。)

### Step 8.4: 验证 build

```bash
cd viewer && npm run build 2>&1 | tail -5
```

Expect:`✓ built`。

### Step 8.5: 手动验证(用户)

- 打开 `http://localhost:8765/` → 透明背景
- 打开 `http://localhost:8765/?bg=222` → 灰底
- 打开 `http://localhost:8765/?bg=#00ff00` → 绿幕(给 OBS 色键抠图用)

## Self-Review

- [ ] config.ts 解析 bg + model 参数
- [ ] pixi-app.ts 接受 ViewerConfig
- [ ] main.ts 读 config 后传给 createPixiApp + live2d.load
- [ ] vite build 通过

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 9: 端到端验证(用户)

**Files:** 无。

### Step 9.1: 确认 Cubism Core 已就位

```bash
ls -lh /Users/geforever/Desktop/Gちゃん/viewer/public/cubismcore/
```

应看到 `live2dcubismcore.min.js`(约 200KB-500KB),不是 `.gitkeep`。

### Step 9.2: build viewer 产物

```bash
cd /Users/geforever/Desktop/Gちゃん/viewer && npm run build
```

Expect:`viewer/dist/index.html` + `viewer/dist/assets/main-<hash>.js` + `viewer/dist/cubismcore/live2dcubismcore.min.js`。

### Step 9.3: 启动后端

```bash
cd /Users/geforever/Desktop/Gちゃん
uv run python -m g_chan
```

启动日志应包含:
- `live2d enabled — expressions=N motions=M`
- `live2d assets mounted at /live2d from Live2D`
- `static viewer mounted at / from viewer/dist`
- `ws server enabled at ws://localhost:8765/ws`

### Step 9.4: 浏览器打开 viewer

http://localhost:8765/

应看到:
- 透明背景上 G 酱 Live2D 模型居中显示
- 自动眨眼 + 呼吸(idle 动画)
- 浏览器 DevTools Console 应有 `ws open`

### Step 9.5: 测试 Twitch 消息触发

主播身份发 `@G酱 嗨` 到 Twitch chat。viewer 浏览器应:
- Console 打印 `← expression smile`(或别的名字)
- Console 打印 `← motion none`(或 tap 等)
- Console 打印 `← speak: 哈喽~`
- 角色嘴动起来(lipsync)+ 听到 TTS 声音 + 看到表情/动作变化

### Step 9.6: OBS 集成(可选)

OBS → Sources → +「Browser Source」→ URL `http://localhost:8765/` → 宽高同直播分辨率 → 勾选 "Shutdown source when not visible"。
透明背景应让角色直接叠在游戏画面上。

### Step 9.7: 重连测试

ctrl+C 关掉 `python -m g_chan`,viewer console 应打印 `ws closed` + `ws reconnect in 1000ms`,且间隔指数增长。重启后端后 viewer 应自动恢复连接(`ws open` 重新出现)。

## Phase 3b 完成定义

- [ ] viewer build 产生 viewer/dist
- [ ] 浏览器访问 http://localhost:8765/ 看到 Live2D 模型
- [ ] Idle 眨眼 + 呼吸自动跑
- [ ] Twitch @G酱 触发后,viewer 浏览器实时:expression 切换 + motion 播放 + TTS 音频 + lipsync 嘴动
- [ ] 后端重启后 viewer 自动重连
- [ ] OBS browser source 透明叠加可用

完成后 G 酱整体 Phase 1-3 全部到位。Phase 4(可选 polish:多模型切换、音量条、心情可视化、stress test 等)按需展开。
