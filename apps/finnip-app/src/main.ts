import "./style.css";
import { Link } from "./link";
import { Mic } from "./mic";
import { Player } from "./player";
import { Holo } from "./holo";
import { Hud } from "./hud";
import { createIcons, Maximize, MessageSquare, MessagesSquare, Minimize, Settings } from "lucide";

createIcons({ icons: { Maximize, MessageSquare, MessagesSquare, Settings } });

type Mode = "conversation" | "single";
type State = "off" | "listening" | "thinking" | "speaking";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const orb = $<HTMLButtonElement>("orb");
const statusEl = $("status");
const power = $<HTMLButtonElement>("power");
const metricsEl = $("metrics");
const net = $("net");
const hud = new Hud($("hud"));
let holo: Holo | null = null;
try {
  holo = new Holo($<HTMLCanvasElement>("holo"), $("orb"));
} catch (err) {
  console.error("sin WebGL", err); // the orb button still works, just without the hologram
}

// Hologram color = the monitors' LED color (sent by the server; remembered while they are off).
function setTheme(rgb: [number, number, number]) {
  holo?.setColor(rgb);
  const [h, s, l] = rgbToHsl(rgb);
  document.documentElement.style.setProperty("--holo", `hsl(${h} ${s}% ${Math.max(l, 45)}%)`);
  try {
    localStorage.setItem("finnip.theme", JSON.stringify(rgb));
  } catch {}
}
function rgbToHsl([r, g, b]: number[]): [number, number, number] {
  [r, g, b] = [r / 255, g / 255, b / 255];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (!d) return [0, 0, Math.round(l * 100)];
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [Math.round((h * 60 + 360) % 360), Math.round(s * 100), Math.round(l * 100)];
}
try {
  const saved = JSON.parse(localStorage.getItem("finnip.theme") || "null");
  if (saved) setTheme(saved);
} catch {}

const settings = { metrics: false };
try {
  Object.assign(settings, JSON.parse(localStorage.getItem("finnip.settings") || "{}"));
} catch {}
const saveSettings = () => {
  try {
    localStorage.setItem("finnip.settings", JSON.stringify(settings));
  } catch {}
};

const link = new Link();
const mic = new Mic();
let player = null as Player | null;
let mode = "conversation" as Mode;
let state = "off" as State;
let speechLevel = 0;
let acceptAudio = true;
const t = { end: 0, transcript: 0, firstAudio: 0 };

const STATUS: Record<State, string> = {
  off: "Toca para hablar",
  listening: "Te escucho",
  thinking: "Pensando…",
  speaking: "Toca para interrumpir",
};

function setState(next: State) {
  state = next;
  document.body.dataset.state = next;
  if (next === "listening" || next === "off") hud.hide(1200); // stats live only while Finnip talks
  statusEl.textContent = !link.online ? "Sin conexión con Finnip" : STATUS[next];
  power.hidden = !(mode === "conversation" && mic.isOpen);
  orb.setAttribute("aria-pressed", String(mic.isOpen));
}

const restingState = (): State => (mic.isOpen ? "listening" : "off");

function getPlayer() {
  if (!player) {
    player = new Player();
    player.onStart = () => {
      mic.setMuted(true); // Finnip never hears itself; interrupt it with a tap
      setState("speaking");
    };
    player.onIdle = () => {
      mic.setMuted(false);
      setState(restingState());
    };
  }
  return player;
}

function showMetrics() {
  metricsEl.hidden = !settings.metrics;
  if (!t.end) return;
  const ms = (x: number) => (x ? `${((x - t.end) / 1000).toFixed(2)} s` : "…");
  metricsEl.textContent = `transcripción ${ms(t.transcript)} · primer audio ${ms(t.firstAudio)}`;
}

// Live audio: frames stream to the server while the user speaks, so it can send partial transcripts.
// The last ~300 ms before the VAD fires are kept here and sent first, so the first syllable is not lost.
const PRE_SPEECH_FRAMES = 10; // Silero v5 frames are 32 ms
const preSpeech: Float32Array[] = [];
let streaming = false;

function abortUtterance() {
  if (!streaming) return;
  streaming = false;
  link.send({ type: "utterance_abort" });
}

function finishUtterance() {
  streaming = false;
  link.send({ type: "utterance_end" });
  t.end = performance.now();
  t.transcript = t.firstAudio = 0;
  showMetrics();
  player?.chime();
  setState("thinking");
}

const handlers = {
  onSpeechStart() {
    if (player?.isSpeaking || !link.online) return;
    streaming = true;
    link.send({ type: "utterance_start" });
    preSpeech.splice(0).forEach((f) => link.sendFrame(f));
  },
  onMisfire() {
    abortUtterance();
  },
  onSpeechEnd() {
    if (!streaming) return;
    if (player?.isSpeaking) return abortUtterance();
    finishUtterance();
    if (mode === "single") void mic.close().then(() => setState(state));
  },
  onFrame(frame: Float32Array) {
    if (streaming) return link.sendFrame(frame);
    preSpeech.push(frame);
    if (preSpeech.length > PRE_SPEECH_FRAMES) preSpeech.shift();
  },
  onLevel(p: number) {
    speechLevel = p;
  },
};

let opening = false;

async function openMic() {
  if (opening) return;
  opening = true;
  try {
    statusEl.textContent = "Permite el micrófono…";
    await mic.open(handlers, () => (statusEl.textContent = "Preparando…"));
    setState("listening");
  } catch (err) {
    console.error(err);
    await mic.close();
    setState("off");
    statusEl.textContent =
      err instanceof DOMException && err.name === "NotAllowedError"
        ? "Sin permiso de micrófono: actívalo en el navegador"
        : "No pude abrir el micrófono";
  } finally {
    opening = false;
  }
}

function interrupt() {
  acceptAudio = false; // drop chunks of the cancelled reply still in flight
  link.send({ type: "interrupt", ...(player?.played() ?? { played_seq: 0, played_ms: 0 }) });
  player?.flush();
  setState(restingState());
}

orb.addEventListener("click", async () => {
  void getPlayer().unlock();
  if (state === "speaking" || state === "thinking") return interrupt();
  if (mic.isOpen) {
    await closeMic();
    return setState("off");
  }
  await openMic();
});

async function closeMic() {
  abortUtterance();
  await mic.close();
}

power.addEventListener("click", async () => {
  if (state === "speaking" || state === "thinking") interrupt();
  await closeMic();
  setState("off");
});

document.querySelectorAll<HTMLButtonElement>(".modes button").forEach((btn) =>
  btn.addEventListener("click", async () => {
    mode = btn.dataset.mode as Mode;
    document.querySelectorAll(".modes button").forEach((b) => b.classList.toggle("on", b === btn));
    if (mic.isOpen) await closeMic();
    setState(state === "listening" ? "off" : state);
  }),
);

link.onStatus = (online) => {
  net.classList.toggle("online", online);
  setState(state);
};

link.onEvent = (e) => {
  switch (e.type) {
    case "transcript":
      t.transcript = performance.now();
      showMetrics();
      if (!e.text) return setState(player?.isSpeaking ? "speaking" : restingState()); // noise: a running reply goes on
      acceptAudio = true;
      setState("thinking");
      break;
    case "done":
      if (state === "thinking" && !player?.isSpeaking) setState(restingState());
      player?.endOfReply();
      break;
    case "theme":
      setTheme(e.rgb);
      break;
    case "stats":
      if (acceptAudio) hud.show(e);
      break;
    case "error":
      statusEl.textContent = e.message;
      break;
  }
};

link.onAudio = (seq, mp3) => {
  if (!acceptAudio) return;
  if (!t.firstAudio && t.end) {
    t.firstAudio = performance.now();
    showMetrics();
  }
  void getPlayer().enqueue(seq, mp3);
};

// Orb reacts to the user's voice while listening and to Finnip's voice while speaking.
const levels = new Uint8Array(128);
(function animate() {
  let level = 0;
  if (state === "speaking" && player) {
    player.analyser.getByteTimeDomainData(levels);
    let sum = 0;
    for (const v of levels) sum += ((v - 128) / 128) ** 2;
    level = Math.min(1, Math.sqrt(sum / levels.length) * 4);
  } else if (state === "listening") {
    level = speechLevel;
  }
  if (holo) {
    holo.state = state;
    holo.shrink = hud.on;
    holo.frame(level);
  }
  requestAnimationFrame(animate);
})();

const clock = $("clock");
setInterval(() => (clock.textContent = new Date().toLocaleTimeString("es-MX", { hour12: false })), 1000);

// Fullscreen (iPhone Safari has no Fullscreen API: there, "Agregar a inicio" already opens full screen).
const fullBtn = $<HTMLButtonElement>("fullscreen");
fullBtn.hidden = !document.fullscreenEnabled;
fullBtn.addEventListener("click", () =>
  document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(),
);
document.addEventListener("fullscreenchange", () => {
  fullBtn.replaceChildren(Object.assign(document.createElement("i"), { dataset: { lucide: "" } }));
  fullBtn.firstElementChild!.setAttribute("data-lucide", document.fullscreenElement ? "minimize" : "maximize");
  createIcons({ icons: { Maximize, Minimize }, root: fullBtn });
});

// Settings
const dialog = $<HTMLDialogElement>("settings");
const metricsInput = $<HTMLInputElement>("opt-metrics");
metricsInput.checked = settings.metrics;
$("settings-btn").addEventListener("click", () => dialog.showModal());
metricsInput.addEventListener("change", () => {
  settings.metrics = metricsInput.checked;
  saveSettings();
  showMetrics();
});

if ("serviceWorker" in navigator) void navigator.serviceWorker.register("/sw.js");
setState("off");
showMetrics();
link.connect();
setTimeout(Mic.preload, 1500);
