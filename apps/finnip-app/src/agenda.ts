// Agenda overlay: the calendar events Finnip was asked about, shown before the voice arrives.
// The hologram fades out underneath (body.agenda-on) and comes back when the agenda closes.
import type { ServerEvent } from "./link";

type Agenda = Extract<ServerEvent, { type: "reminders" }>;
type Item = Agenda["items"][number];
const MAX_ROWS = 10;
const FADE_MS = 600; // matches the .agenda transition
const el = document.getElementById("agenda")!;
let timer = 0;

function node(tag: string, className = "", text = "") {
  const n = document.createElement(tag);
  if (className) n.className = className;
  n.textContent = text;
  return n;
}

export function showAgenda({ title, items }: Agenda) {
  clearTimeout(timer);
  const shown = items.slice(0, MAX_ROWS);
  const count = `${String(items.length).padStart(2, "0")} ${items.length === 1 ? "evento" : "eventos"}`;
  const head = node("header", "ag-head");
  head.append(node("span", "ag-kicker", "Agenda"), node("h2", "ag-title", title), node("span", "ag-count", count), node("i", "ag-rule"));

  const days = new Map<string, Item[]>();
  for (const item of shown) days.set(item.date, [...(days.get(item.date) ?? []), item]);
  const list = node("div", "ag-list");
  let order = 0; // stagger: each day and row slides in a little after the previous one
  for (const [date, events] of days) {
    const day = node("section", "ag-day");
    day.style.setProperty("--i", String(order++));
    const stamp = node("div", "ag-date");
    // "mié 11 nov" -> "mié · nov": the day number is already shown big above it.
    stamp.append(node("b", "", String(Number(date.slice(8)))), node("small", "", events[0].day.replace(/ \d+ /, " · ")));
    const rows = node("div", "ag-events");
    for (const event of events) {
      const row = node("p", "ag-ev");
      row.style.setProperty("--i", String(order++));
      row.append(node("time", "", event.time || "Todo el día"), node("span", "", event.name));
      rows.append(row);
    }
    day.append(stamp, rows);
    list.append(day);
  }
  if (!items.length) list.append(node("p", "ag-note", "Sin eventos en este periodo"));
  if (items.length > MAX_ROWS) list.append(node("p", "ag-note", `+${items.length - MAX_ROWS} más`));

  el.replaceChildren(head, list);
  el.hidden = false;
  requestAnimationFrame(() => {
    el.classList.add("on");
    document.body.classList.add("agenda-on");
  });
  timer = window.setTimeout(hideAgenda, Math.min(30000, 12000 + shown.length * 1000));
}

export function hideAgenda() {
  clearTimeout(timer);
  el.classList.remove("on");
  document.body.classList.remove("agenda-on");
  timer = window.setTimeout(() => (el.hidden = true), FADE_MS);
}
