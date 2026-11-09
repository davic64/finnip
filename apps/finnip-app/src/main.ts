import "./style.css";
import { Link } from "./link";
import { Mic } from "./mic";
import { Player } from "./player";

type Mode = "conversation" | "single";
type State = "off" | "listening" | "thinking" | "speaking";

const BARGE_IN_MS = 700; // continuous speech needed to interrupt Finnip by voice (echo-proofing)
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const orb = $<HTMLButtonElement>("orb");
const statusEl = $("status");
const power = $<HTMLButtonElement>("power");
const log = $("log");
const metricsEl = $("metrics");
const net = $("net");

const settings = { bargeIn: true, metrics: false };
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
let bargeTimer = 0;
let bargePlayed: { played_seq: number; played_ms: number } | null = null;
let finnipBubble: HTMLElement | null = null;
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
  statusEl.textContent = !link.online ? "Sin conexión con Finnip" : STATUS[next];
  power.hidden = !(mode === "conversation" && mic.isOpen);
  orb.setAttribute("aria-pressed", String(mic.isOpen));
}

const restingState = (): State => (mic.isOpen ? "listening" : "off");

function getPlayer() {
  if (!player) {
    player = new Player();
    player.onStart = () => {
      mic.setStrict(true);
      setState("speaking");
    };
    player.onIdle = () => {
      mic.setStrict(false);
      setState(restingState());
    };
  }
  return player;
}

function bubble(who: "user" | "finnip", text: string) {
  const el = document.createElement("p");
  el.className = `bubble ${who}`;
  el.textContent = text;
  log.append(el);
  while (log.children.length > 12) log.firstElementChild!.remove();
  log.scrollTop = log.scrollHeight;
  return el;
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
let liveBubble: HTMLElement | null = null;
let lastUserBubble: HTMLElement | null = null;

function endLiveBubble(remove: boolean) {
  if (remove) liveBubble?.remove();
  else liveBubble?.classList.remove("partial");
  liveBubble = null;
}

function abortUtterance() {
  if (!streaming) return;
  streaming = false;
  link.send({ type: "utterance_abort" });
  endLiveBubble(true);
}

function finishUtterance(extra: object = {}) {
  streaming = false;
  link.send({ type: "utterance_end", ...extra });
  t.end = performance.now();
  t.transcript = t.firstAudio = 0;
  showMetrics();
  if (!("barge_in" in extra)) {
    player?.chime();
    setState("thinking");
  }
}

const handlers = {
  onSpeechStart() {
    const finnipTalking = player?.isSpeaking;
    if (finnipTalking && (mode !== "conversation" || !settings.bargeIn)) return;
    if (!link.online) return;
    streaming = true;
    link.send({ type: "utterance_start" });
    preSpeech.splice(0).forEach((f) => link.sendFrame(f));
    if (!finnipTalking) {
      liveBubble = bubble("user", "…");
      liveBubble.classList.add("partial");
      return;
    }
    clearTimeout(bargeTimer);
    bargeTimer = window.setTimeout(() => {
      bargePlayed = player!.played();
      void player!.pause();
      statusEl.textContent = "Te escucho";
      liveBubble = bubble("user", "…");
      liveBubble.classList.add("partial");
    }, BARGE_IN_MS);
  },
  onMisfire() {
    clearTimeout(bargeTimer);
    abortUtterance();
    if (bargePlayed) {
      bargePlayed = null;
      void player?.resume();
      setState("speaking");
    }
  },
  onSpeechEnd() {
    clearTimeout(bargeTimer);
    if (!streaming) return;
    if (bargePlayed) return finishUtterance({ barge_in: true, ...bargePlayed });
    if (player?.isSpeaking) return abortUtterance(); // too short to count as an interruption
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
  clearTimeout(bargeTimer);
  bargePlayed = null;
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
    case "partial":
      if (liveBubble) liveBubble.textContent = e.text;
      log.scrollTop = log.scrollHeight;
      break;
    case "transcript":
      t.transcript = performance.now();
      showMetrics();
      if (bargePlayed) {
        bargePlayed = null;
        player?.flush();
      }
      if (!e.text) {
        endLiveBubble(true);
        return setState(restingState());
      }
      acceptAudio = true;
      // A continuation after a pause comes back merged with the previous phrase: show one bubble.
      if (e.merged && lastUserBubble !== liveBubble) lastUserBubble?.remove();
      if (liveBubble) liveBubble.textContent = e.text;
      else liveBubble = bubble("user", e.text);
      lastUserBubble = liveBubble;
      endLiveBubble(false);
      finnipBubble = null;
      setState("thinking");
      break;
    case "reply_text":
      if (!acceptAudio) return;
      finnipBubble ??= bubble("finnip", "");
      finnipBubble.textContent = `${finnipBubble.textContent} ${e.text}`.trim();
      break;
    case "resume":
      endLiveBubble(true);
      bargePlayed = null;
      void player?.resume();
      setState("speaking");
      break;
    case "done":
      if (state === "thinking" && !player?.isSpeaking) setState(restingState());
      player?.endOfReply();
      break;
    case "error":
      bubble("finnip", e.message).classList.add("error");
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
  orb.style.setProperty("--level", level.toFixed(3));
  requestAnimationFrame(animate);
})();

// Settings
const dialog = $<HTMLDialogElement>("settings");
const bargeInput = $<HTMLInputElement>("opt-barge");
const metricsInput = $<HTMLInputElement>("opt-metrics");
bargeInput.checked = settings.bargeIn;
metricsInput.checked = settings.metrics;
$("settings-btn").addEventListener("click", () => dialog.showModal());
bargeInput.addEventListener("change", () => {
  settings.bargeIn = bargeInput.checked;
  saveSettings();
});
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
