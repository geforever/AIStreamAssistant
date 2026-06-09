import * as PIXI from "pixi.js";
import { Live2DModel } from "pixi-live2d-display/cubism4";

// pixi-live2d-display 内部需要全局 PIXI(它没把 PIXI 作为 ES import)
(window as unknown as { PIXI: typeof PIXI }).PIXI = PIXI;

// 标准命名 fallback — 没有 LipSync group 时尝试用这两个常见名
const MOUTH_PARAM_FALLBACKS = ["ParamMouthOpenY", "PARAM_MOUTH_OPEN_Y"];

export class Live2DController {
  private model: Live2DModel | null = null;
  private app: PIXI.Application | null = null;
  private audioCtx: AudioContext | null = null;
  // 从 model3.json Groups[LipSync].Ids 解析,加载时确定 —
  // 不同模型嘴型 param 名不一样(Cubism 2 用 PARAM_MOUTH_OPEN_Y,Cubism 4 标准用 ParamMouthOpenY)
  private mouthParams: string[] = [];

  // 由后端 init 消息同步;applyExpression 后用于调度回退到 default
  private defaultExpression = "";
  private expressionRevertMs = 0;
  private revertTimer: number | null = null;

  setDefaults(defaultExpression: string, expressionRevertMs: number): void {
    this.defaultExpression = defaultExpression;
    this.expressionRevertMs = expressionRevertMs;
  }

  /** 用户手势触发时调一次 — 在没有用户交互前 AudioContext 无法 resume,
   * 直接结果是 analyser 没数据 → lipsync 嘴不动。
   */
  async unlockAudio(): Promise<void> {
    if (!this.audioCtx) this.audioCtx = new AudioContext();
    if (this.audioCtx.state === "suspended") {
      try {
        await this.audioCtx.resume();
      } catch (e) {
        console.warn("unlockAudio resume failed:", e);
      }
    }
    console.log("audio unlocked, state =", this.audioCtx.state);
  }

  async load(app: PIXI.Application, modelUrl: string): Promise<void> {
    this.app = app;
    const model = await Live2DModel.from(modelUrl);
    this.model = model;
    this.mouthParams = this._resolveMouthParams(model);
    console.log("lipsync mouth params:", this.mouthParams);
    app.stage.addChild(model);
    this._fit();
    window.addEventListener("resize", () => this._fit());
  }

  private _resolveMouthParams(model: Live2DModel): string[] {
    // pixi-live2d-display 已从 model3.json Groups[LipSync].Ids 预计算到 lipSyncIds
    const ids = (model.internalModel as unknown as {
      motionManager?: { lipSyncIds?: string[] };
    }).motionManager?.lipSyncIds;
    return ids?.length ? ids : MOUTH_PARAM_FALLBACKS;
  }

  private _fit(): void {
    if (!this.model || !this.app) return;
    const m = this.model;
    // renderer.width / .height 是 backbuffer 物理像素(retina 2x),
    // renderer.screen 才是逻辑/CSS 像素 — fit 必须用 screen,否则在 retina 上会放大 2 倍
    const cw = this.app.renderer.screen.width;
    const ch = this.app.renderer.screen.height;
    // internalModel.width / height 是模型逻辑画布(常量),跟 anchor 对齐;
    // m.width/m.height 是 bounds(只含可见 drawable,可能比逻辑画布小)→ fit 算不准
    const im = m.internalModel as unknown as { width: number; height: number };
    const scale = Math.min(cw / im.width, ch / im.height) * 0.9;
    m.scale.set(scale);
    m.anchor.set(0.5, 0.5);
    m.x = cw / 2;
    m.y = ch / 2;
    console.log("fit:", { cw, ch, imW: im.width, imH: im.height, scale });
  }

  applyExpression(name: string): void {
    if (!this.model) return;

    // 新表情到达 → 取消上一次还没触发的回退计时
    if (this.revertTimer !== null) {
      window.clearTimeout(this.revertTimer);
      this.revertTimer = null;
    }

    if (!name || name === "None" || name === "none") return;

    this._setExpression(name);

    // 非 default 且配置了回退间隔 → 调度恢复
    if (this.expressionRevertMs > 0 && name !== this.defaultExpression) {
      this.revertTimer = window.setTimeout(() => {
        this.revertTimer = null;
        this._setExpression(this.defaultExpression);
      }, this.expressionRevertMs);
    }
  }

  private _setExpression(name: string): void {
    if (!this.model) return;
    if (!name) {
      // 空 default → 清掉所有表情,回到模型基础参数状态
      const em = (this.model.internalModel as unknown as {
        motionManager?: { expressionManager?: { resetExpression?: () => void } };
      }).motionManager?.expressionManager;
      em?.resetExpression?.();
      return;
    }
    try {
      this.model.expression(name);
    } catch (e) {
      console.warn("expression failed:", name, e);
    }
  }

  applyMotion(group: string): void {
    if (!this.model || !group || group === "None" || group === "none") return;
    try {
      this.model.motion(group);
    } catch (e) {
      console.warn("motion failed:", group, e);
    }
  }

  /** 播放 base64 mp3 + 实时音量驱动嘴型(ParamMouthOpenY)。
   *
   * 浏览器自动播放策略要求页面有过用户手势才允许 AudioContext 启动。
   * 首次失败时 console.warn,不抛 — 视为 lipsync 退化,音频继续播放,嘴不动。
   */
  async speak(base64Audio: string, format: string): Promise<void> {
    if (!this.model) return;

    const bytes = Uint8Array.from(atob(base64Audio), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: `audio/${format}` });
    const url = URL.createObjectURL(blob);

    try {
      await this._playWithLipsync(url);
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  private async _playWithLipsync(url: string): Promise<void> {
    const audio = new Audio(url);
    // 不要设 crossOrigin — blob: URL 是同源,设了反而让浏览器进 CORS 模式,
    // blob 不发 CORS 头 → analyser buffer 被视为 tainted 静音返 0(声音照常出,只 lipsync 死)

    // 拿到 AudioContext 并解锁(自动播放策略可能 suspended)
    if (!this.audioCtx) {
      this.audioCtx = new AudioContext();
    }
    console.log("lipsync: audioCtx.state before resume =", this.audioCtx.state);
    if (this.audioCtx.state === "suspended") {
      try {
        await this.audioCtx.resume();
      } catch (e) {
        console.warn("audio context resume failed, lipsync disabled:", e);
      }
    }
    console.log("lipsync: audioCtx.state after resume =", this.audioCtx.state);

    let analyser: AnalyserNode | null = null;
    let data: Uint8Array<ArrayBuffer> | null = null;

    if (this.audioCtx.state === "running") {
      try {
        const source = this.audioCtx.createMediaElementSource(audio);
        analyser = this.audioCtx.createAnalyser();
        analyser.fftSize = 256;
        // 串联 source → analyser → destination
        // 不能用 source 两路 fan-out(analyser 一路没下游 → 引擎可能优化掉不算 FFT,读到全 0)
        source.connect(analyser);
        analyser.connect(this.audioCtx.destination);
        data = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));
        console.log("lipsync: analyser ready, frequencyBinCount =", analyser.frequencyBinCount);
      } catch (e) {
        console.warn("analyser setup failed, no lipsync:", e);
        analyser = null;
      }
    } else {
      console.warn("lipsync: audioCtx not running — no analyser, mouth won't move");
    }

    const model = this.model!;

    // 钩 internalModel.beforeModelUpdate(不是 model.on):
    // - pixi-live2d-display 0.4.x 没有 "afterModelUpdate" 事件,事件全在 internalModel 上 emit
    // - "beforeModelUpdate" 在 motion/expression/eyeblink/focus/breath/physics/pose 全部
    //   设置完参数之后、model.update() 把参数 flush 到 GPU 之前 — 这时 setParameterValueById
    //   就是覆盖在所有自然动作之上,本帧 render 用我们的嘴型值
    let maxObserved = 0;
    let hookCalls = 0;
    const injectMouthParam = () => {
      hookCalls++;
      if (!analyser || !data) return;
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i];
      const avg = sum / data.length / 255;
      const mouthOpen = Math.min(1, avg * 2.5);
      if (mouthOpen > maxObserved) maxObserved = mouthOpen;
      this._setMouth(model, mouthOpen);
    };
    const internal = model.internalModel as unknown as {
      on: (ev: string, fn: () => void) => void;
      off: (ev: string, fn: () => void) => void;
    };
    internal.on("beforeModelUpdate", injectMouthParam);

    try {
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => {
          console.log("lipsync: audio.onended fired");
          resolve();
        };
        audio.onerror = () => reject(new Error("audio playback error"));
        audio.play()
          .then(() => console.log("lipsync: audio.play() resolved, paused =", audio.paused, "duration =", audio.duration))
          .catch(reject);
      });
    } catch (e) {
      console.warn("audio play failed:", e);
    } finally {
      internal.off("beforeModelUpdate", injectMouthParam);
      this._setMouth(model, 0);
      console.log(
        "lipsync done, max mouth =", maxObserved.toFixed(3),
        ", hook fired", hookCalls, "times",
      );
    }
  }

  private _setMouth(model: Live2DModel, value: number): void {
    const core = (model.internalModel as unknown as {
      coreModel: { setParameterValueById?: (id: string, v: number) => void };
    }).coreModel;
    if (!core.setParameterValueById) return;
    for (const id of this.mouthParams) {
      core.setParameterValueById(id, value);
    }
  }
}
