// Cards at the top right of the stage: a device changed (by voice, Telegram or by hand).
import type { ServerEvent } from "./link";

type Device = Extract<ServerEvent, { type: "device" }>;
const FADE_MS = 400; // matches the .card transition
const box = document.getElementById("cards")!;
const cards = new Map<string, HTMLElement>();

/** The card for `key` (created if needed), faded in now and out after `ms`. */
function place(key: string, className: string, ms: number) {
  let card = cards.get(key);
  if (!card) {
    card = document.createElement("div");
    box.append(card);
    cards.set(key, card);
  }
  const el = card;
  el.className = className + (el.classList.contains("on") ? " on" : "");
  requestAnimationFrame(() => el.classList.add("on"));
  clearTimeout(Number(el.dataset.timer));
  el.dataset.timer = String(
    setTimeout(() => {
      el.classList.remove("on");
      setTimeout(() => {
        if (el.classList.contains("on")) return; // shown again while fading out
        el.remove();
        cards.delete(key);
      }, FADE_MS);
    }, ms),
  );
  return el;
}

export function showCard(d: Device) {
  const card = place(d.id, "card", 4000);
  const dot = document.createElement("i");
  dot.style.background = !d.on ? "transparent" : d.rgb ? `rgb(${d.rgb.join(",")})` : "var(--holo)";
  const name = Object.assign(document.createElement("span"), { textContent: d.name });
  const value = Object.assign(document.createElement("b"), {
    textContent: !d.on ? "Apagado" : d.brightness != null ? `${d.brightness} %` : "Encendido",
  });
  card.replaceChildren(dot, name, value);
}


