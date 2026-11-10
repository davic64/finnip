// Runtime assets the app loads from its own origin (no CDN):
// /vad/: the VAD's worklet, Silero model and onnxruntime wasm.
// /hands/: MediaPipe's vision wasm and the hand landmark model (pinned by SHA-256, downloaded once).
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

function copy(out, files) {
  mkdirSync(out, { recursive: true });
  for (const f of files) copyFileSync(f, `${out}/${f.split("/").pop()}`);
}

copy("dist/vad", [
  "node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js",
  "node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx",
  "node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm",
  "node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs",
]);

const wasm = "node_modules/@mediapipe/tasks-vision/wasm";
copy("dist/hands", ["vision_wasm_internal.js", "vision_wasm_internal.wasm",
  "vision_wasm_module_internal.js", "vision_wasm_module_internal.wasm"].map((f) => `${wasm}/${f}`));

const MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
const MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1";
const cached = "node_modules/.cache/finnip/hand_landmarker.task";
if (!existsSync(cached)) {
  const response = await fetch(MODEL_URL);
  if (!response.ok) throw new Error(`hand model: HTTP ${response.status}`);
  mkdirSync("node_modules/.cache/finnip", { recursive: true });
  writeFileSync(cached, Buffer.from(await response.arrayBuffer()));
}
const hash = createHash("sha256").update(readFileSync(cached)).digest("hex");
if (hash !== MODEL_SHA256) throw new Error(`hand model: unexpected SHA-256 ${hash}`);
copy("dist/hands", [cached]);
