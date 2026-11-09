// Microphone + Silero VAD in the browser. close() stops every track, so the OS mic indicator turns off.
import { MicVAD } from "@ricky0123/vad-web";
import * as ort from "onnxruntime-web/wasm";

ort.env.wasm.numThreads = 1; // no cross-origin isolation, so no wasm threads

export type MicHandlers = {
  onSpeechStart: () => void;
  onSpeechEnd: (audio: Float32Array) => void;
  onMisfire: () => void;
  onLevel: (speechProbability: number) => void;
  onFrame: (frame: Float32Array) => void;
};

export class Mic {
  private vad: MicVAD | null = null;
  private stream: MediaStream | null = null;

  get isOpen() {
    return this.vad !== null;
  }

  /** Asks for the mic first (inside the tap, so the prompt shows at once), then loads the VAD. */
  async open(h: MicHandlers, onPermission: () => void = () => {}) {
    if (this.vad) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    onPermission();
    const stream = this.stream;
    this.vad = await MicVAD.new({
      model: "v5",
      baseAssetPath: "/vad/",
      onnxWASMBasePath: "/vad/",
      positiveSpeechThreshold: 0.6,
      negativeSpeechThreshold: 0.45,
      redemptionMs: 600, // silence that ends a phrase: lower = faster turns, higher = fewer cut-offs
      minSpeechMs: 250,
      preSpeechPadMs: 300,
      getStream: async () => stream,
      pauseStream: async () => {},
      resumeStream: async (s) => s,
      onSpeechStart: h.onSpeechStart,
      onSpeechEnd: h.onSpeechEnd,
      onVADMisfire: h.onMisfire,
      onFrameProcessed: (p, frame) => {
        h.onLevel(p.isSpeech);
        h.onFrame(frame);
      },
      startOnLoad: true,
    });
  }

  /** Silence the mic track while Finnip talks, so its own voice never comes back as the user's. */
  setMuted(muted: boolean) {
    this.stream?.getAudioTracks().forEach((t) => (t.enabled = !muted));
    // A muted mic only feeds silence: pause the VAD model too (it ran ~31 inferences/s for nothing).
    // pauseStream is a no-op above, so the stream and its permission stay open.
    void (muted ? this.vad?.pause() : this.vad?.start());
  }

  /** Warm the HTTP cache so the first tap does not wait for the ~4 MB VAD runtime. */
  static preload() {
    for (const f of ["silero_vad_v5.onnx", "ort-wasm-simd-threaded.wasm", "ort-wasm-simd-threaded.mjs", "vad.worklet.bundle.min.js"])
      void fetch(`/vad/${f}`).catch(() => {});
  }

  async close() {
    const vad = this.vad;
    this.vad = null;
    await vad?.destroy();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }
}
