import type { ServerMessage } from "./types";

type Handler = (msg: ServerMessage) => void | Promise<void>;

/** WebSocket 客户端 — 自动重连(指数退避 1s → 30s)。
 *
 * 连上后退避归零;关闭事件触发重连(除非手动 close())。
 */
export class WSClient {
  private ws: WebSocket | null = null;
  private backoffMs = 1000;
  private readonly maxBackoffMs = 30_000;
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
