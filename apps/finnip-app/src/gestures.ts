// Hand gestures for the open 3D part, from MediaPipe Gesture Recognizer: 21 landmarks per hand (normalized
// camera image) plus its trained gesture label ("Closed_Fist", "Open_Palm", "None"...).
//   pinch and move (thumb + index together): turn the part; down = look from above, sideways = spin it
//   pinch with both hands, apart or together: zoom in or out
//   open hand held still 1 s: back to the starting view
//   fist twice in a row (fist, open, fist): close the part
// Pure functions (tests/gestures.test.mjs); hands.ts feeds them camera frames.
export type Point = { x: number; y: number };
export type TrackedHand = { label: string; points: Point[]; gesture?: string; score?: number };
export type GestureAction =
  | { kind: "rotate"; dx: number; dy: number } // in fractions of the image, already mirrored like a mirror
  | { kind: "zoom"; factor: number }
  | { kind: "reset" }
  | { kind: "close" };

const PINCH_ON = 0.38; // thumb-index gap / hand size to start a pinch
const PINCH_OFF = 0.55; // ...and to release it (hysteresis: no flicker at the threshold)
const SMOOTH = 0.7; // landmark jitter (higher follows faster)
const STILL_MS = 1000; // open hand this long without moving: reset the view
const STILL_RANGE = 0.03; // ...within this much of the image
const DOUBLE_FIST_MS = 1500; // second fist must start this soon after the first
const STABLE_FRAMES = 4; // fist / not-fist must hold this many frames to count (~130 ms; a half-closed hand flickered)
const FIST_SCORE = 0.8; // the classifier must be this sure: a half-closed hand scored lower

const dist = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
const handSize = (h: Point[]) => dist(h[0], h[9]) || 1e-3; // wrist to middle knuckle
const pinchGap = (h: Point[]) => dist(h[4], h[8]) / handSize(h);
const pinchPoint = (h: Point[]): Point => ({ x: (h[4].x + h[8].x) / 2, y: (h[4].y + h[8].y) / 2 });
export const isFist = (h: TrackedHand) => h.gesture === "Closed_Fist" && (h.score ?? 1) >= FIST_SCORE;
export const isOpen = (h: TrackedHand) => h.gesture === "Open_Palm";

export class GestureTracker {
  private pinching = new Map<string, boolean>();
  private smooth = new Map<string, Point>();
  private last = new Map<string, Point>();
  private span: number | null = null;
  private palm: { t: number; x: number; y: number }[] = []; // one open hand, recent positions
  private stillDone = false;
  private fist = false; // debounced fist state of the single hand
  private flips = 0; // frames in a row disagreeing with `fist`
  private fistStarts: number[] = [];

  reset() {
    this.pinching.clear();
    this.smooth.clear();
    this.last.clear();
    this.span = null;
    this.palm = [];
    this.stillDone = false;
    this.fist = false;
    this.flips = 0;
    this.fistStarts = [];
  }

  update(hands: TrackedHand[], now: number): GestureAction[] {
    const actions: GestureAction[] = [];
    const seen = new Set(hands.map((h) => h.label));
    for (const label of [...this.pinching.keys()]) if (!seen.has(label)) this.forget(label);
    const pinched: { label: string; at: Point }[] = [];
    for (const hand of hands) {
      const { label, points } = hand;
      const was = this.pinching.get(label) ?? false;
      const gap = pinchGap(points);
      // A fist is never a pinch, even with the thumb touching the index.
      const pinching = !isFist(hand) && (was ? gap < PINCH_OFF : gap < PINCH_ON);
      this.pinching.set(label, pinching);
      if (!pinching) {
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

    const single = pinched.length === 0 && hands.length === 1 ? hands[0] : null;
    if (this.doubleFist(single, now)) actions.push({ kind: "close" });
    if (this.stillPalm(single, now)) actions.push({ kind: "reset" });
    return actions;
  }

  /** Fist, open, fist within DOUBLE_FIST_MS, each state held STABLE_FRAMES frames. */
  private doubleFist(hand: TrackedHand | null, now: number) {
    const fist = !!hand && isFist(hand);
    if (fist === this.fist) {
      this.flips = 0;
      return false;
    }
    if (++this.flips < STABLE_FRAMES) return false;
    this.fist = fist;
    this.flips = 0;
    if (!fist) return false;
    this.fistStarts = [...this.fistStarts.filter((t) => now - t <= DOUBLE_FIST_MS), now];
    if (this.fistStarts.length < 2) return false;
    this.fistStarts = [];
    return true;
  }

  /** An open hand kept still for STILL_MS; once per open hand. */
  private stillPalm(hand: TrackedHand | null, now: number) {
    if (!hand || !isOpen(hand)) {
      this.palm = [];
      this.stillDone = false;
      return false;
    }
    if (this.stillDone) return false;
    const knuckle = hand.points[9];
    this.palm = [...this.palm.filter((p) => now - p.t <= STILL_MS), { t: now, x: knuckle.x, y: knuckle.y }];
    if (now - this.palm[0].t < STILL_MS * 0.95) return false;
    const span = (k: "x" | "y") => Math.max(...this.palm.map((p) => p[k])) - Math.min(...this.palm.map((p) => p[k]));
    if (span("x") >= STILL_RANGE || span("y") >= STILL_RANGE) return false;
    this.stillDone = true;
    return true;
  }

  private forget(label: string) {
    this.pinching.delete(label);
    this.smooth.delete(label);
    this.last.delete(label);
  }
}
