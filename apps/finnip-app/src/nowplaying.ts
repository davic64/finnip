// Now playing on the Alexa speaker, shown only while a song plays: round cover inside a progress ring
// (plus a slowly turning dashed ring), title, artist, time and a segmented volume meter. No box.
// The server sends a snapshot on every change; progress moves locally between snapshots.
import type { ServerEvent } from "./link";

type NowPlaying = Extract<ServerEvent, { type: "now_playing" }>;
const el = document.getElementById("nowplaying")!;
const R = 44; // progress ring radius in the 100x100 viewBox
const RING = 2 * Math.PI * R;
const VOLUME_STEPS = 12;
let tick = 0;
let hideTimer = 0;
let shownKey = ""; // same song: update in place instead of replaying the entrance

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function build() {
  el.innerHTML = `
    <div class="np-dial">
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <defs><clipPath id="np-clip"><circle cx="50" cy="50" r="33"/></clipPath></defs>
        <circle class="np-track" cx="50" cy="50" r="${R}"/>
        <circle class="np-progress" cx="50" cy="50" r="${R}" stroke-dasharray="${RING}" stroke-dashoffset="${RING}"/>
        <circle class="np-spin" cx="50" cy="50" r="38"/>
        <circle class="np-disc" cx="50" cy="50" r="33"/>
        <image class="np-cover" x="17" y="17" width="66" height="66" clip-path="url(#np-clip)" preserveAspectRatio="xMidYMid slice"/>
      </svg>
    </div>
    <div class="np-text">
      <span class="np-kicker">Audio · Alexa</span>
      <strong class="np-title"></strong>
      <span class="np-artist"></span>
      <span class="np-rule"></span>
      <div class="np-meta"><span class="np-time"></span><span class="np-vol">VOL <i></i><b></b></span></div>
    </div>`;
  const meter = el.querySelector(".np-vol i")!;
  for (let i = 0; i < VOLUME_STEPS; i++) {
    const bar = document.createElement("u");
    bar.style.height = `${3 + i * 0.6}px`; // rising bars, 3px to ~10px
    meter.append(bar);
  }
}

export function showNowPlaying(np: NowPlaying) {
  clearInterval(tick);
  clearTimeout(hideTimer);
  if (!np.active || np.state !== "playing") {
    el.classList.remove("on");
    hideTimer = window.setTimeout(() => {
      el.hidden = true;
      shownKey = "";
    }, 700);
    return;
  }
  const key = `${np.title}|${np.artist}`;
  if (key !== shownKey || el.hidden) {
    build();
    shownKey = key;
  }
  const $ = <T extends Element>(s: string) => el.querySelector<T>(s)!;
  $(".np-title").textContent = np.title ?? "";
  $(".np-artist").textContent = np.artist ?? "";
  const cover = $<SVGImageElement>(".np-cover");
  if (np.image) cover.setAttribute("href", np.image);
  else cover.removeAttribute("href");
  const lit = Math.round(((np.volume ?? 0) / 100) * VOLUME_STEPS);
  el.querySelectorAll(".np-vol u").forEach((u, i) => u.classList.toggle("lit", i < lit));
  $(".np-vol b").textContent = `${np.volume ?? "--"}`;

  // Position = reported position + time since it was reported.
  const at = np.position_at ? Date.parse(np.position_at) : Date.now();
  const progress = $<SVGCircleElement>(".np-progress");
  const time = $(".np-time");
  const update = () => {
    const pos = Math.min(np.duration ?? 0, (np.position ?? 0) + (Date.now() - at) / 1000);
    progress.style.strokeDashoffset = String(np.duration ? RING * (1 - pos / np.duration) : RING);
    time.textContent = np.duration ? `${clock(pos)} / ${clock(np.duration)}` : "";
  };
  el.hidden = false;
  requestAnimationFrame(() => {
    el.classList.add("on");
    update();
  });
  tick = window.setInterval(update, 1000);
}
