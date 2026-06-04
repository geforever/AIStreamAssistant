/** 浏览器 URL 参数解析。
 *
 * ?bg=#222 / ?bg=222 → 开发时给个可见底色,默认透明(OBS browser source 模式)
 * ?model=/live2d/Other/Other.model3.json → 覆盖默认模型路径
 */
export interface ViewerConfig {
  backgroundColor: number | null;
  backgroundAlpha: number;
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
  const m = s.match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (!m) return null;
  let hex = m[1];
  if (hex.length === 3) {
    hex = hex.split("").map((c) => c + c).join("");
  }
  return parseInt(hex, 16);
}
