// The VAD loads its worklet, Silero model and onnxruntime wasm at runtime from /vad/.
import { copyFileSync, mkdirSync } from "node:fs";

const out = "dist/vad";
mkdirSync(out, { recursive: true });
for (const f of [
  "node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js",
  "node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx",
  "node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm",
  "node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs",
]) copyFileSync(f, `${out}/${f.split("/").pop()}`);
