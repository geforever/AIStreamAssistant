/** Phase 3a 后端 → 前端协议(跟 src/g_chan/viewer_sink/ws_sink.py 保持一致)。 */
export type ServerMessage =
  | { type: "expression"; name: string }
  | { type: "motion"; name: string }
  | { type: "speak"; audio: string; format: string; text: string }
  | { type: "ping" };
