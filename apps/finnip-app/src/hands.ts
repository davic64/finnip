// Camera + MediaPipe Gesture Recognizer for the open 3D part (desktop overlay): hand landmarks plus a trained
// gesture label per hand. The camera is on only while a part is open; frames stay on the Mac: the model
// and its wasm are served by this app (/hands/), no CDN.
import { FilesetResolver, GestureRecognizer } from "@mediapipe/tasks-vision";
import { GestureTracker, type GestureAction } from "./gestures";

const FRAME_MS = 33; // ~30 detections per second

export class Hands {
  private recognizer: GestureRecognizer | null = null;
  private stream: MediaStream | null = null;
  private video = Object.assign(document.createElement("video"), { muted: true, playsInline: true });
  private tracker = new GestureTracker();
  private running = false;
  private last = 0;

  constructor(
    private onAction: (action: GestureAction) => void,
    private onStatus: (on: boolean, error?: string) => void,
  ) {}

  async start() {
    if (this.running) return;
    this.running = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" }, audio: false,
      });
      if (!this.running) return stream.getTracks().forEach((t) => t.stop()); // closed meanwhile
      this.stream = stream;
      this.video.srcObject = stream;
      await this.video.play();
      this.recognizer ??= await GestureRecognizer.createFromOptions(await FilesetResolver.forVisionTasks("/hands"), {
        baseOptions: { modelAssetPath: "/hands/gesture_recognizer.task", delegate: "GPU" },
        runningMode: "VIDEO",
        numHands: 2,
      });
      if (!this.running) return;
      this.onStatus(true);
      requestAnimationFrame((t) => this.frame(t));
    } catch (err) {
      this.stop();
      this.onStatus(false, err instanceof Error ? err.message : String(err));
    }
  }

  /** One camera frame as base64 JPEG (longest side maxSide), from the running camera or opened just for it. */
  async snapshot(maxSide = 1024): Promise<string> {
    let video = this.video;
    let temporary: MediaStream | null = null;
    if (!this.stream) {
      temporary = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720, facingMode: "user" }, audio: false });
      video = Object.assign(document.createElement("video"), { muted: true, playsInline: true, srcObject: temporary });
      await video.play();
      await new Promise((r) => setTimeout(r, 400)); // let the exposure settle
    }
    try {
      const scale = Math.min(1, maxSide / Math.max(video.videoWidth, video.videoHeight));
      const canvas = Object.assign(document.createElement("canvas"), {
        width: Math.round(video.videoWidth * scale), height: Math.round(video.videoHeight * scale),
      });
      canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL("image/jpeg", 0.85).split(",", 2)[1];
    } finally {
      temporary?.getTracks().forEach((t) => t.stop());
    }
  }

  stop() {
    this.running = false;
    this.stream?.getTracks().forEach((t) => t.stop()); // camera light off
    this.stream = null;
    this.video.srcObject = null;
    this.tracker.reset();
    this.onStatus(false);
  }

  private frame(now: number) {
    if (!this.running || !this.recognizer) return;
    requestAnimationFrame((t) => this.frame(t));
    if (now - this.last < FRAME_MS || this.video.readyState < 2) return;
    this.last = now;
    const result = this.recognizer.recognizeForVideo(this.video, now);
    const hands = result.landmarks.map((points, i) => ({
      label: result.handedness[i]?.[0]?.categoryName ?? String(i),
      points,
      gesture: result.gestures[i]?.[0]?.categoryName,
    }));
    for (const action of this.tracker.update(hands, now)) this.onAction(action);
  }
}
