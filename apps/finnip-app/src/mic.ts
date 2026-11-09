// Microphone + Silero VAD in the browser. close() stops every track, so the OS mic indicator turns off.
import { MicVAD } from "@ricky0123/vad-web";
import * as ort from "onnxruntime-web/wasm";

ort.env.wasm.numThreads = 1; // no cross-origin isolation, so no wasm threads

export type MicHandlers = {
  onSpeechStart: () => void;
  onSpeechEnd: (audio: Float32Array) => void;
  onMisfire: () => void;
  onLevel: (speechProbability: number) => void;
};

export class Mic {
  private vad: MicVAD | null = null;
  private stream: MediaStream | null = null;

  get isOpen() {
    return this.vad !== null;
  }

  async open(h: MicHandlers) {
    if (this.vad) return;
    this.vad = await MicVAD.new({
      model: "v5",
      baseAssetPath: "/vad/",
      onnxWASMBasePath: "/vad/",
      positiveSpeechThreshold: 0.6,
      negativeSpeechThreshold: 0.45,
      redemptionMs: 550, // silence that ends a phrase: lower = faster turns, higher = fewer cut-offs
      minSpeechMs: 250,
      preSpeechPadMs: 300,
      getStream: async () => {
        this.stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        return this.stream;
      },
      pauseStream: async () => {},
      resumeStream: async (s) => s,
      onSpeechStart: h.onSpeechStart,
      onSpeechEnd: h.onSpeechEnd,
      onVADMisfire: h.onMisfire,
      onFrameProcessed: (p) => h.onLevel(p.isSpeech),
      startOnLoad: true,
    });
  }

  async close() {
    const vad = this.vad;
    this.vad = null;
    await vad?.destroy();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }
}
