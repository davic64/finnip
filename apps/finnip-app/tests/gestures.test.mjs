// Hand gestures on the 3D part. Run: npm test (node --test, TS stripped by Node).
import { test } from "node:test";
import assert from "node:assert/strict";
const { GestureTracker } = await import("../src/gestures.ts");

/** A right hand around (x, y): "open", "fist", or "pinch" (thumb and index tips together), with the label
 *  the gesture classifier would give it. */
function hand(pose, x = 0.5, y = 0.5) {
  const p = Array.from({ length: 21 }, () => ({ x, y: y + 0.3 }));
  const set = (i, dx, dy) => (p[i] = { x: x + dx, y: y + 0.3 + dy });
  set(0, 0, 0);
  for (const [k, [tip, pip]] of [[8, 6], [12, 10], [16, 14], [20, 18]].map((f, i) => [i, f])) {
    const dx = (k - 1.5) * 0.04;
    set(tip - 3, dx, -0.2); // knuckle; the middle one (9) gives a hand size of 0.2
    set(pip, dx, -0.28);
    set(tip, dx, pose === "fist" ? -0.2 : -0.42);
  }
  set(4, -0.15, -0.15);
  if (pose === "pinch") {
    set(8, -0.06, -0.33);
    set(4, -0.05, -0.33);
  }
  if (pose === "fist") set(4, -0.05, -0.2); // the thumb rests on the folded index: close to a pinch
  const gesture = { open: "Open_Palm", fist: "Closed_Fist", pinch: "None" }[pose];
  return { label: "Right", points: p, gesture };
}

const frames = (t, poses, start, step = 40) => poses.flatMap((pose, i) => t.update([hand(pose)], start + i * step));

test("a fist with the thumb on the index is not a pinch; one fist does nothing", () => {
  const t = new GestureTracker();
  assert.deepEqual(frames(t, ["fist", "fist", "fist", "fist"], 0).filter((a) => a.kind !== "reset"), []);
  t.update([hand("fist", 0.3)], 200); // a moving fist does not turn the part
  assert.deepEqual(t.update([hand("fist", 0.2)], 240), []);
});

test("fist twice in a row closes the part", () => {
  const t = new GestureTracker();
  const got = frames(t, ["open", "fist", "fist", "fist", "open", "open", "open", "fist", "fist"], 0);
  assert.deepEqual(got, [{ kind: "close" }]);
});

test("two fists too far apart, or a one-frame flicker, do not close", () => {
  const t = new GestureTracker();
  assert.deepEqual(frames(t, ["fist", "fist", "open", "open"], 0), []);
  assert.deepEqual(frames(t, ["fist", "fist"], 2000), []); // 2 s later: a new first fist
  const u = new GestureTracker();
  assert.deepEqual(frames(u, ["fist", "fist", "fist", "open", "fist", "fist"], 0), []); // open for one frame only
});

test("pinch and move turns the part like a mirror; letting go stops", () => {
  const t = new GestureTracker();
  assert.deepEqual(t.update([hand("pinch", 0.5, 0.5)], 0), []);
  const [turn] = t.update([hand("pinch", 0.4, 0.6)], 33);
  assert.equal(turn.kind, "rotate");
  assert.ok(turn.dx > 0, "hand to the right in the user's view (x lower in the image) turns right");
  assert.ok(turn.dy > 0, "hand down tilts the part to show its top");
  assert.deepEqual(t.update([hand("open", 0.4, 0.6)], 66), []);
  assert.deepEqual(t.update([hand("open", 0.2, 0.6)], 99), []);
});

test("two pinching hands zoom; apart is closer", () => {
  const t = new GestureTracker();
  const both = (gap) => [{ ...hand("pinch", 0.5 - gap), label: "Left" }, hand("pinch", 0.5 + gap)];
  assert.deepEqual(t.update(both(0.1), 0), []);
  const [zoom] = t.update(both(0.2), 33);
  assert.equal(zoom.kind, "zoom");
  assert.ok(zoom.factor > 1);
  const [out] = t.update(both(0.05), 66);
  assert.ok(out.factor < 1);
});

test("open hand held still resets the view once", () => {
  const t = new GestureTracker();
  const open = (ms, x = 0.5) => t.update([hand("open", x)], ms);
  assert.deepEqual(open(0), []);
  assert.deepEqual(open(500), []);
  assert.deepEqual(open(1000), [{ kind: "reset" }]);
  assert.deepEqual(open(1500), []);
  t.update([], 1600);
  assert.deepEqual([open(2000, 0.5), open(2500, 0.6), open(3000, 0.5)].flat(), []); // moving: no reset
});
