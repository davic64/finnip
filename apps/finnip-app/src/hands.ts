// Camera + MediaPipe Hand Landmarker for the open 3D part (desktop overlay). The camera is on only while
// a part is open; frames stay on the Mac: the model and its wasm are served by this app (/hands/), no CDN.
import { FilesetResolver, HandLandmarker } from "@mediapipe/tasks-vision";
import { GestureTracker, type GestureAction } from "./gestures";

const FRAME_MS = 33; // ~30 detections per second

export class Hands {
  private landmarker: HandLandmarker | null = null;
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
      this.landmarker ??= await HandLandmarker.createFromOptions(await FilesetResolver.forVisionTasks("/hands"), {
        baseOptions: { modelAssetPath: "/hands/hand_landmarker.task", delegate: "GPU" },
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

  stop() {
    this.running = false;
    this.stream?.getTracks().forEach((t) => t.stop()); // camera light off
    this.stream = null;
    this.video.srcObject = null;
    this.tracker.reset();
    this.onStatus(false);
  }

  private frame(now: number) {
    if (!this.running || !this.landmarker) return;
    requestAnimationFrame((t) => this.frame(t));
    if (now - this.last < FRAME_MS || this.video.readyState < 2) return;
    this.last = now;
    const result = this.landmarker.detectForVideo(this.video, now);
    const hands = result.landmarks.map((points, i) => ({
      label: result.handedness[i]?.[0]?.categoryName ?? String(i),
      points,
    }));
    for (const action of this.tracker.update(hands, now)) this.onAction(action);
  }
}
