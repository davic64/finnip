// WebSocket /ws client (protocol in openspec design.md, decisión 6). Reconnects on its own.
export type ServerEvent =
  | { type: "ready"; version: number }
  | { type: "transcript"; text: string }
  | { type: "reply_text"; seq: number; text: string }
  | { type: "audio"; seq: number; format: string }
  | { type: "resume" }
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
      ws.send(JSON.stringify({ type: "hello", client: "pwa", version: 1 }));
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

  /** One utterance: PCM16 LE mono 16 kHz, then utterance_end with any extra fields (barge_in...). */
  sendUtterance(audio: Float32Array, extra: object = {}) {
    if (!this.online) return false;
    const pcm = new Int16Array(audio.length);
    for (let i = 0; i < audio.length; i++) pcm[i] = Math.max(-1, Math.min(1, audio[i])) * 0x7fff;
    const chunk = 16000 * 2; // 1 s per frame keeps frames small for the ESP32-style server buffer
    const bytes = new Uint8Array(pcm.buffer);
    for (let i = 0; i < bytes.length; i += chunk) this.ws!.send(bytes.slice(i, i + chunk));
    this.ws!.send(JSON.stringify({ type: "utterance_end", ...extra }));
    return true;
  }
}
