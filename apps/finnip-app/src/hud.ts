// Server stats HUD: four arc gauges around the hologram, shown only while Finnip talks about them.
export type Stats = {
  cpu: number;
  ram_used: number;
  ram_total: number;
  disk_used: number;
  disk_total: number;
  temp: number | null;
  load: number;
  cores: number;
  uptime: number;
};

const R = 42;
const ARC = 2 * Math.PI * R * 0.75; // 270° gauge

function gauge(label: string, pct: number, value: string, detail: string) {
  const el = document.createElement("div");
  el.className = "gauge";
  el.innerHTML = `
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <circle class="track" cx="50" cy="50" r="${R}" stroke-dasharray="${ARC} 999" />
      <circle class="val" cx="50" cy="50" r="${R}" stroke-dasharray="0 999" />
      <circle class="ticks" cx="50" cy="50" r="${R - 7}" />
    </svg>
    <b></b><span>${label}</span><small>${detail}</small>`;
  const val = el.querySelector<SVGCircleElement>(".val")!;
  const num = el.querySelector("b")!;
  const target = Math.max(0, Math.min(100, pct));
  const start = performance.now();
  (function count(now: number) {
    const k = Math.min(1, (now - start) / 1100);
    const e = 1 - (1 - k) ** 3;
    val.setAttribute("stroke-dasharray", `${(ARC * target * e) / 100} 999`);
    num.textContent = k < 1 ? value.replace(/[\d.]+/, (n) => (parseFloat(n) * e).toFixed(n.includes(".") ? 1 : 0)) : value;
    if (k < 1) requestAnimationFrame(count);
  })(start);
  el.classList.toggle("hot", target >= 85);
  return el;
}

function uptime(s: number) {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  return d ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`;
}

export class Hud {
  private hideTimer = 0;
  constructor(private el: HTMLElement) {}

  get on() {
    return this.el.classList.contains("on");
  }

  show(s: Stats) {
    clearTimeout(this.hideTimer);
    const pct = (a: number, b: number) => (b ? (a / b) * 100 : 0);
    const temp = s.temp ?? 0;
    this.el.replaceChildren(
      gauge("CPU", s.cpu, `${s.cpu}%`, `${s.cores} núcleos`),
      gauge("RAM", pct(s.ram_used, s.ram_total), `${s.ram_used.toFixed(1)}`, `de ${s.ram_total} GB`),
      gauge("DISCO", pct(s.disk_used, s.disk_total), `${Math.round(pct(s.disk_used, s.disk_total))}%`, `${s.disk_used} / ${s.disk_total} GB`),
      gauge("TEMP", temp, s.temp === null ? "--" : `${temp}°`, "°C núcleo"),
      Object.assign(document.createElement("p"), {
        className: "hud-foot",
        textContent: `CARGA ${s.load.toFixed(2)}  ·  ACTIVO ${uptime(s.uptime)}  ·  FINNIP-SRV`,
      }),
    );
    this.el.hidden = false;
    requestAnimationFrame(() => this.el.classList.add("on"));
  }

  hide(delay = 0) {
    clearTimeout(this.hideTimer);
    this.hideTimer = window.setTimeout(() => {
      this.el.classList.remove("on");
      this.hideTimer = window.setTimeout(() => (this.el.hidden = true), 500);
    }, delay);
  }
}
