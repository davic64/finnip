import "./style.css";
import { Link } from "./link";
import { Mic } from "./mic";
import { Player } from "./player";
import { glowColor, Holo } from "./holo";
import { Hud } from "./hud";
import { showCard } from "./cards";
import { showAgenda } from "./agenda";
import { showNowPlaying } from "./nowplaying";
import { MusicNotice, sceneFor } from "./desktop";
import { Hands } from "./hands";
import { PartView } from "./part";
import { createIcons, Maximize, MessageSquare, MessagesSquare, Minimize, Settings } from "lucide";

createIcons({ icons: { Maximize, MessageSquare, MessagesSquare, Settings } });

type Mode = "conversation" | "single";
type State = "off" | "standby" | "listening" | "thinking" | "speaking";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const orb = $<HTMLButtonElement>("orb");
const statusEl = $("status");
const metricsEl = $("metrics");
const net = $("net");
const hud = new Hud($("hud"));
// Inside the macOS app: transparent overlay with scenes (desktop.ts) instead of the full-screen UI.
const desktop = new URLSearchParams(location.search).has("desktop");
if (desktop) document.documentElement.classList.add("desktop");
let holo: Holo | null = null;
try {
  holo = new Holo($<HTMLCanvasElement>("holo"), $("orb"), desktop);
} catch (err) {
  console.error("sin WebGL", err); // the orb button still works, just without the hologram
}

// 3D part viewer (desktop only). Its box is the only place where the macOS app takes the mouse: the page
// reports it through the one command the app allows it (part_box); the gateway learns whether a part is
// open, so short view orders ("vista de arriba") go to the viewer instead of Hermes.
type TauriIpc = { invoke: (cmd: string, args: object) => Promise<unknown> };
const tauri = (window as unknown as { __TAURI_INTERNALS__?: TauriIpc }).__TAURI_INTERNALS__;
let partView: PartView | null = null;
// Hand gestures on the open part; the camera runs only while a part is open.
const hands = desktop
  ? new Hands(
      (a) => {
        if (a.kind === "rotate") partView?.rotateBy(a.dx, a.dy);
        else if (a.kind === "zoom") partView?.zoomBy(a.factor);
        else partView?.view(a.kind);
      },
      (on, error) => {
        partView?.setHands(on, error);
        if (error) console.error("cámara", error);
      },
    )
  : null;
if (desktop && holo) {
  try {
    partView = new PartView($("part"), $("part-hit"), $("part-label"), (open, rect) => {
      link.send({ type: "part_open", open });
      void tauri?.invoke("part_box", { rect }).catch(() => {});
      if (open) void hands?.start();
      else hands?.stop();
    });
  } catch (err) {
    console.error("sin visor de piezas", err);
  }
}
// Hologram color = the monitors' LED color (sent by the server; remembered while they are off).
function setTheme(rgb: [number, number, number]) {
  holo?.setColor(rgb);
  partView?.setColor(glowColor(rgb));
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
const mic = new Mic(!desktop); // desktop: no voice processing, so other audio is not ducked
let player = null as Player | null;
let mode = "conversation" as Mode;
let state = "off" as State;
let speechLevel = 0;
let acceptAudio = true;
const t = { end: 0, transcript: 0, firstAudio: 0 };

const STATUS: Record<State, string> = {
  off: "Toca para hablar",
  standby: "Di «Finnip» o toca",
  listening: "Te escucho",
  thinking: "Pensando…",
  speaking: "Toca para interrumpir",
};

// Conversation mode falls asleep after SLEEP_MS without speech: the mic stays open in standby and
// only a phrase that starts with "Finnip" (checked by the server) or a tap wakes it up again.
const SLEEP_MS = 2000;
let asleep = false;
let sleepTimer = 0;

function setState(next: State) {
  state = next;
  document.body.dataset.state = next;
  clearTimeout(sleepTimer);
  if (next === "listening" && mode === "conversation")
    sleepTimer = window.setTimeout(() => {
      if (state !== "listening" || streaming) return;
      asleep = true;
      setState("standby");
    }, SLEEP_MS);
  if (next === "listening" || next === "off" || next === "standby") hud.hide(1200); // stats live only while Finnip talks
  statusEl.textContent = !link.online ? "Sin conexión con Finnip" : STATUS[next];
  orb.setAttribute("aria-pressed", String(mic.isOpen));
}

// While the Echo plays, every turn ends in standby: the song's lyrics must not talk to Finnip.
// "Finnip, …" or a tap wakes it up as usual.
let musicOn = false;
function restingState(): State {
  if (mic.isOpen && musicOn && mode === "conversation") asleep = true;
  return !mic.isOpen ? "off" : asleep ? "standby" : "listening";
}

function getPlayer() {
  if (!player) {
    player = new Player();
    player.onStart = () => {
      // Finnip never hears itself; interrupt it with a tap. Desktop: no taps, so the mic stays open and
      // only "Finnip, …" counts while it speaks (the server drops its own voice as echo).
      if (!desktop) mic.setMuted(true);
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
// Standby: "Finnip" opens the phrase, so a long sound (music) is cut into windows the server
// transcribes once each, instead of one endless phrase.
const WAKE_WINDOW_MS = 4000;
// Each window starts with the last ~1 s of the previous one, so a "Finnip" cut at the edge is whole.
const OVERLAP_FRAMES = 32; // Silero v5 frames are 32 ms
const recentFrames: Float32Array[] = [];
let wakeWindow = 0;
let bargeIn = false; // this phrase started while Finnip was speaking (desktop)

function startUtterance() {
  streaming = true;
  bargeIn = !!player?.isSpeaking;
  const guarded = asleep || bargeIn; // only a phrase with "Finnip" counts
  link.send({ type: "utterance_start", ...(guarded ? { wake: true } : {}) });
  clearTimeout(wakeWindow);
  if (guarded)
    wakeWindow = window.setTimeout(() => {
      if (!streaming || !(asleep || bargeIn)) return;
      finishUtterance();
      startUtterance(); // still sounding: next window
      recentFrames.forEach((f) => link.sendFrame(f));
    }, WAKE_WINDOW_MS);
}
function abortUtterance() {
  if (!streaming) return;
  streaming = false;
  clearTimeout(wakeWindow);
  link.send({ type: "utterance_abort" });
}
function finishUtterance() {
  streaming = false;
  clearTimeout(wakeWindow);
  if (bargeIn) // while it speaks: "Finnip, para" stops it, "Finnip, …" asks something new
    return link.send({ type: "utterance_end", wake: true, barge_in: true, ...(player?.played() ?? { played_seq: 0, played_ms: 0 }) });
  if (asleep) return link.send({ type: "utterance_end", wake: true }); // the server checks for "Finnip"
  link.send({ type: "utterance_end" });
  t.end = performance.now();
  t.transcript = t.firstAudio = 0;
  showMetrics();
  player?.chime();
  setState("thinking");
}

const handlers = {
  onSpeechStart() {
    if ((player?.isSpeaking && !desktop) || !link.online) return;
    startUtterance();
    preSpeech.splice(0).forEach((f) => link.sendFrame(f));
  },
  onMisfire() {
    abortUtterance();
    if (state === "listening") setState("listening"); // re-arm the sleep timer
  },
  onSpeechEnd() {
    if (!streaming) return;
    if (player?.isSpeaking && !desktop) return abortUtterance();
    finishUtterance();
    if (mode === "single") void mic.close().then(() => setState(state));
  },
  onFrame(frame: Float32Array) {
    recentFrames.push(frame);
    if (recentFrames.length > OVERLAP_FRAMES) recentFrames.shift();
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
    setState(restingState());
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
  if (state === "standby") {
    asleep = false;
    return setState("listening");
  }
  if (mic.isOpen) {
    await closeMic();
    return setState("off");
  }
  asleep = false;
  await openMic();
});

async function closeMic() {
  abortUtterance();
  await mic.close();
}

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
    case "wake":
      if (player?.isSpeaking) {
        acceptAudio = false; // barge-in: silence it now; a new reply's transcript turns audio back on
        player.flush();
      }
      asleep = false;
      void getPlayer().unlock(); // allowed without a tap while the mic is capturing
      player?.chime();
      setState("listening");
      break;
    case "announce": // Finnip speaks first (printer notices): play it even if no reply is expected
      acceptAudio = true;
      break;
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
    case "device":
      showCard(e);
      break;
    case "now_playing":
      musicOn = e.active && e.state === "playing";
      if (!desktop) showNowPlaying(e);
      else if (musicNotice.shouldShow(e)) {
        showNowPlaying(e); // a new song: shown for a moment, then it fades
        clearTimeout(noticeTimer);
        noticeTimer = window.setTimeout(() => showNowPlaying({ ...e, active: false }), MUSIC_NOTICE_MS);
      } else if (!musicOn) showNowPlaying(e); // paused or stopped: hide it
      if (musicOn && state === "listening" && !streaming) setState(restingState());
      break;
    case "reminders":
      if (acceptAudio) showAgenda(e);
      break;
    case "stats":
      if (acceptAudio) hud.show(e);
      break;
    case "part":
      void partView?.show(e).catch((err) => console.error("pieza", err));
      break;
    case "part_view":
      partView?.view(e.view);
      break;
    case "photo_request": // finnip_parts look: one camera frame, only because the user asked
      if (!hands) break;
      void hands.snapshot().then(
        (jpeg) => {
          link.send({ type: "photo", id: e.id, jpeg });
          document.body.classList.add("photo-taken");
          setTimeout(() => document.body.classList.remove("photo-taken"), 900);
        },
        (err) => link.send({ type: "photo", id: e.id, error: `Cámara: ${err instanceof Error ? err.message : err}` }),
      );
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

// Desktop: music notice timing, and the hologram keeps drawing while it fades out (0.6 s in CSS).
const MUSIC_NOTICE_MS = 6000;
const musicNotice = new MusicNotice();
let noticeTimer = 0;
let hiddenSince = 0;
function holoFading() {
  if (document.body.dataset.scene !== "hidden") return (hiddenSince = 0), true;
  hiddenSince ||= performance.now();
  return performance.now() - hiddenSince < 700;
}
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
  if (desktop) {
    const scene = sceneFor(state, hud.on || document.body.classList.contains("agenda-on"), partView?.open);
    if (document.body.dataset.scene !== scene) document.body.dataset.scene = scene;
    // No drawing while nothing is shown, nor behind an open part.
    if (holo) holo.paused = (scene === "hidden" && !holoFading()) || scene === "part";
  }
  if (holo) {
    holo.state = state === "standby" ? "off" : state;
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

// Desktop app: always listening in standby; the app's menu bar and shortcut call these (webview eval).
if (desktop) {
  const talk = () => {
    void getPlayer().unlock();
    if (!mic.isOpen) return void openMic().then(talk);
    if (state === "speaking" || state === "thinking") return interrupt(); // the shortcut silences it
    if (state === "listening" && !asleep) {
      asleep = true; // pressed again while listening: back to standby
      return setState("standby");
    }
    asleep = false; // the next phrase is for Finnip, no wake word needed
    player?.chime();
    setState("listening");
  };
  const mute = (on: boolean) => {
    if (on) return void closeMic().then(() => setState("off"));
    asleep = true;
    void openMic();
  };
  const visible = (on: boolean) => document.documentElement.classList.toggle("desktop-off", !on);
  Object.assign(window, { finnipDesktop: { talk, mute, visible } });
  asleep = true;
  void openMic();
}
// Mic already allowed: open straight into standby, waiting for "Finnip". Otherwise the first tap
// asks for permission (browsers only show that prompt after a gesture).
if (!desktop) void (async () => {
  try {
    const perm = await navigator.permissions.query({ name: "microphone" as PermissionName });
    if (perm.state !== "granted" || mode !== "conversation") return;
  } catch {
    return; // no Permissions API for the mic (older Safari): wait for the tap
  }
  asleep = true;
  await openMic();
})();
