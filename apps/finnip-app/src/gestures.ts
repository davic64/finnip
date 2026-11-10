// Hand gestures for the open 3D part, from MediaPipe's 21 hand landmarks (normalized camera image).
//   pinch and move (thumb + index together): turn the part; down = look from above, sideways = spin it
//   pinch with both hands, apart or together: zoom in or out
//   open hand held 1 s: back to the starting view;  fist held half a second: close the part
// Pure functions (tests/gestures.test.mjs); hands.ts feeds them camera frames.
export type Point = { x: number; y: number };
export type TrackedHand = { label: string; points: Point[] };
export type GestureAction =
  | { kind: "rotate"; dx: number; dy: number } // in fractions of the image, already mirrored like a mirror
  | { kind: "zoom"; factor: number }
  | { kind: "reset" }
  | { kind: "close" };

const PINCH_ON = 0.3; // thumb-index gap / hand size to start a pinch
const PINCH_OFF = 0.45; // ...and to release it (hysteresis: no flicker at the threshold)
const HOLD_MS = { open: 1000, fist: 500 };
const SMOOTH = 0.5; // landmark jitter
const FINGERS: [number, number][] = [[8, 6], [12, 10], [16, 14], [20, 18]]; // tip, middle joint

const dist = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
const handSize = (h: Point[]) => dist(h[0], h[9]) || 1e-3; // wrist to middle knuckle
const pinchGap = (h: Point[]) => dist(h[4], h[8]) / handSize(h);
const pinchPoint = (h: Point[]): Point => ({ x: (h[4].x + h[8].x) / 2, y: (h[4].y + h[8].y) / 2 });

/** Every finger straight (tip farther from the wrist than its middle joint) and the thumb apart. */
export function isOpen(h: Point[]) {
  return FINGERS.every(([tip, pip]) => dist(h[0], h[tip]) > dist(h[0], h[pip]) * 1.1) && pinchGap(h) > 0.6;
}

/** At least three fingers curled (tip closer to the wrist than its middle joint): a loose fist counts. */
export function isFist(h: Point[]) {
  return FINGERS.filter(([tip, pip]) => dist(h[0], h[tip]) < dist(h[0], h[pip])).length >= 3;
}

export class GestureTracker {
  private pinching = new Map<string, boolean>();
  private smooth = new Map<string, Point>();
  private last = new Map<string, Point>();
  private span: number | null = null;
  private hold: { kind: "open" | "fist"; since: number; fired: boolean } | null = null;

  reset() {
    this.pinching.clear();
    this.smooth.clear();
    this.last.clear();
    this.span = null;
    this.hold = null;
  }

  update(hands: TrackedHand[], now: number): GestureAction[] {
    const actions: GestureAction[] = [];
    const seen = new Set(hands.map((h) => h.label));
    for (const label of [...this.pinching.keys()]) if (!seen.has(label)) this.forget(label);
    const pinched: { label: string; at: Point }[] = [];
    for (const { label, points } of hands) {
      const was = this.pinching.get(label) ?? false;
      const gap = pinchGap(points);
      const now_pinching = was ? gap < PINCH_OFF : gap < PINCH_ON;
      this.pinching.set(label, now_pinching);
      if (!now_pinching) {
        this.smooth.delete(label);
        this.last.delete(label);
        continue;
      }
      const raw = pinchPoint(points);
      const prev = this.smooth.get(label);
      const at = prev ? { x: prev.x + (raw.x - prev.x) * SMOOTH, y: prev.y + (raw.y - prev.y) * SMOOTH } : raw;
      this.smooth.set(label, at);
      pinched.push({ label, at });
    }

    if (pinched.length >= 2) {
      const span = dist(pinched[0].at, pinched[1].at);
      if (this.span && span > 0.01) actions.push({ kind: "zoom", factor: span / this.span });
      this.span = span;
      this.last.clear(); // two hands zoom; they do not also turn the part
    } else {
      this.span = null;
      if (pinched.length === 1) {
        const { label, at } = pinched[0];
        const prev = this.last.get(label);
        // The camera sees the user from the front: moving the hand to the right lowers x in the image.
        if (prev) actions.push({ kind: "rotate", dx: -(at.x - prev.x), dy: at.y - prev.y });
        this.last.set(label, at);
      }
    }

    const kind = pinched.length === 0 && hands.length === 1
      ? (isFist(hands[0].points) ? "fist" : isOpen(hands[0].points) ? "open" : null)
      : null;
    if (!kind) this.hold = null;
    else if (this.hold?.kind !== kind) this.hold = { kind, since: now, fired: false };
    else if (!this.hold.fired && now - this.hold.since >= HOLD_MS[kind]) {
      this.hold.fired = true;
      actions.push({ kind: kind === "fist" ? "close" : "reset" });
    }
    return actions;
  }

  private forget(label: string) {
    this.pinching.delete(label);
    this.smooth.delete(label);
    this.last.delete(label);
  }
}
