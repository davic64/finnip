// Hand gestures on the 3D part. Run: npm test (node --test, TS stripped by Node).
import { test } from "node:test";
import assert from "node:assert/strict";
const { GestureTracker, isFist, isOpen } = await import("../src/gestures.ts");

/** A right hand around (x, y): "open", "fist", or "pinch" (thumb and index tips together). */
function hand(pose, x = 0.5, y = 0.5) {
  const p = Array.from({ length: 21 }, () => ({ x, y: y + 0.3 })); // all at the wrist to start
  const set = (i, dx, dy) => (p[i] = { x: x + dx, y: y + 0.3 + dy });
  set(0, 0, 0);
  set(9, 0, -0.2); // middle knuckle: hand size 0.2
  for (const [k, [tip, pip]] of [[8, 6], [12, 10], [16, 14], [20, 18]].map((f, i) => [i, f])) {
    const dx = (k - 1.5) * 0.04;
    const curled = pose === "fist" || (pose === "pinch" && tip === 8);
    set(pip, dx, -0.28);
    set(tip, dx, curled ? -0.15 : -0.42);
  }
  set(4, -0.15, -0.15); // thumb tip apart
  if (pose === "pinch") {
    set(8, -0.06, -0.2);
    set(4, -0.05, -0.2);
  }
  return p;
}

test("open hand, fist and pinch are told apart", () => {
  assert.equal(isOpen(hand("open")), true);
  assert.equal(isFist(hand("open")), false);
  assert.equal(isFist(hand("fist")), true);
  assert.equal(isOpen(hand("fist")), false);
  assert.equal(isOpen(hand("pinch")), false);
  assert.equal(isFist(hand("pinch")), false);
});

test("pinch and move turns the part like a mirror; letting go stops", () => {
  const t = new GestureTracker();
  assert.deepEqual(t.update([{ label: "Right", points: hand("pinch", 0.5, 0.5) }], 0), []); // grabbed
  const [turn] = t.update([{ label: "Right", points: hand("pinch", 0.4, 0.6) }], 33);
  assert.equal(turn.kind, "rotate");
  assert.ok(turn.dx > 0, "hand to the right in the user's view (x lower in the image) turns right");
  assert.ok(turn.dy > 0, "hand down tilts the part to show its top");
  assert.deepEqual(t.update([{ label: "Right", points: hand("open", 0.4, 0.6) }], 66), []);
  assert.deepEqual(t.update([{ label: "Right", points: hand("open", 0.2, 0.6) }], 99), []); // no pinch, no turn
});

test("two pinching hands zoom; apart is closer", () => {
  const t = new GestureTracker();
  const both = (gap) => [
    { label: "Left", points: hand("pinch", 0.5 - gap, 0.5) },
    { label: "Right", points: hand("pinch", 0.5 + gap, 0.5) },
  ];
  assert.deepEqual(t.update(both(0.1), 0), []);
  const [zoom] = t.update(both(0.2), 33);
  assert.equal(zoom.kind, "zoom");
  assert.ok(zoom.factor > 1);
  const [out] = t.update(both(0.05), 66);
  assert.ok(out.factor < 1);
});

test("open hand for a second resets the view, fist for half a second closes, once each", () => {
  const t = new GestureTracker();
  const open = (ms) => t.update([{ label: "Right", points: hand("open") }], ms);
  assert.deepEqual(open(0), []);
  assert.deepEqual(open(500), []);
  assert.deepEqual(open(1000), [{ kind: "reset" }]);
  assert.deepEqual(open(1500), []); // not again while it stays open
  const fist = (ms) => t.update([{ label: "Right", points: hand("fist") }], ms);
  assert.deepEqual(fist(2000), []);
  assert.deepEqual(fist(2499), []);
  assert.deepEqual(fist(2500), [{ kind: "close" }]);
  assert.deepEqual(t.update([], 3100), []); // hand gone
});
