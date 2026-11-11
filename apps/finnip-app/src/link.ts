import type { Stats } from "./hud";

// WebSocket /ws client (server side: voice-gateway Session). Reconnects on its own.
export type ServerEvent =
  | { type: "ready"; version: number }
  | { type: "partial"; text: string }
  | { type: "transcript"; text: string; merged?: boolean }
  | { type: "reply_text"; seq: number; text: string }
  | { type: "audio"; seq: number; format: string }
  | { type: "resume" }
  | { type: "wake" }
  | { type: "announce"; text: string }
  | { type: "enroll"; step?: number; total?: number; text?: string; done?: boolean }
  | { type: "project_request"; id: string; action: string; name?: string; repo?: string; request?: string; allow?: string[] }
  | { type: "theme"; rgb: [number, number, number] }
  | {
      type: "now_playing"; active: boolean; state: string; title: string | null; artist: string | null;
      album: string | null; image: string | null; volume: number | null; duration: number | null;
      position: number | null; position_at: string | null;
    }
  | { type: "device"; id: string; name: string; on: boolean; brightness: number | null; rgb: [number, number, number] | null }
  | ({ type: "stats" } & Stats)
  | { type: "reminders"; title: string; items: { name: string; when: string; date: string; day: string; time: string }[] }
  | { type: "part"; slug: string; version: number; name: string; size_mm: number[] | null; url: string }
  | { type: "part_view"; view: string }
  | { type: "photo_request"; id: string }
  | { type: "done" }
  | { type: "error"; message: string };

export class Link {
  private ws: WebSocket | null = null;
  private pendingAudioSeq: number | null = null;
  private retry = 500;
  onEvent: (e: ServerEvent) => void = () => {};
  onAudio: (seq: number, mp3: ArrayBuffer) => void = () => {};
  onStatus: (online: boolean) => void = () => {};

  connect() {
    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      this.retry = 500;
      this.onStatus(true);
      // "desktop": the macOS overlay, which shows 3D parts and has the camera (the gateway sends it those).
      const client = new URLSearchParams(location.search).has("desktop") ? "desktop" : "pwa";
      ws.send(JSON.stringify({ type: "hello", client, version: 1 }));
    };
    ws.onmessage = (msg) => {
      if (msg.data instanceof ArrayBuffer) {
        if (this.pendingAudioSeq !== null) this.onAudio(this.pendingAudioSeq, msg.data);
        this.pendingAudioSeq = null;
        return;
      }
      const event = JSON.parse(msg.data) as ServerEvent;
      if (event.type === "audio") this.pendingAudioSeq = event.seq;
      else this.onEvent(event);
    };
    ws.onclose = () => {
      this.onStatus(false);
      this.ws = null;
      setTimeout(() => this.connect(), this.retry);
      this.retry = Math.min(this.retry * 2, 8000);
    };
    this.ws = ws;
  }

  get online() {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  send(obj: object) {
    if (this.online) this.ws!.send(JSON.stringify(obj));
  }

  /** One live audio frame: Float32 [-1, 1] at 16 kHz, sent as PCM16 LE. */
  sendFrame(frame: Float32Array) {
    if (!this.online) return;
    const pcm = new Int16Array(frame.length);
    for (let i = 0; i < frame.length; i++) pcm[i] = Math.max(-1, Math.min(1, frame[i])) * 0x7fff;
    this.ws!.send(pcm.buffer);
  }
}
