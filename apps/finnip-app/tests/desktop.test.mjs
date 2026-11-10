// Desktop overlay scenes. Run: npm test (node --test, TS stripped by Node).
import { test } from "node:test";
import assert from "node:assert/strict";

const { sceneFor, MusicNotice, partPose, dragPose, PART_START } = await import("../src/desktop.ts");

test("nothing on screen at rest, the corner while talking, the center with a panel", () => {
  assert.equal(sceneFor("standby", false), "hidden");
  assert.equal(sceneFor("off", false), "hidden");
  for (const state of ["listening", "thinking", "speaking"]) assert.equal(sceneFor(state, false), "corner");
  assert.equal(sceneFor("speaking", true), "center"); // server stats or agenda
  assert.equal(sceneFor("standby", true), "center"); // the panel stays a moment after the reply
});

test("music notice only when a new song starts playing", () => {
  const notice = new MusicNotice();
  const song = (title, state = "playing") => ({ active: true, state, title, artist: "Nils Frahm" });
  assert.equal(notice.shouldShow(song("Says")), true);
  assert.equal(notice.shouldShow(song("Says")), false); // same song, position updates
  assert.equal(notice.shouldShow(song("Says", "paused")), false);
  assert.equal(notice.shouldShow(song("Says")), false); // resumed: same song
  assert.equal(notice.shouldShow(song("Re")), true);
  assert.equal(notice.shouldShow({ active: false, state: "idle", title: null, artist: null }), false);
});
test("an open part takes the center over everything else", () => {
  assert.equal(sceneFor("standby", false, true), "part");
  assert.equal(sceneFor("speaking", true, true), "part");
});
test("spoken views turn the part; zoom and pitch stay within limits", () => {
  const top = partPose({ ...PART_START, spin: true }, "top");
  assert.deepEqual([top.pitch, top.yaw, top.spin], [Math.PI / 2, 0, false]);
  assert.equal(partPose(PART_START, "spin").spin, true);
  assert.equal(partPose(partPose(PART_START, "spin"), "still").spin, false);
  let pose = PART_START;
  for (let i = 0; i < 20; i++) pose = partPose(pose, "closer");
  assert.equal(pose.zoom, 4);
  assert.deepEqual(partPose(pose, "reset"), PART_START);
  assert.equal(partPose(PART_START, "close"), PART_START); // closing is the viewer's job
  assert.equal(dragPose(PART_START, 0, 10_000).pitch, Math.PI / 2);
  assert.equal(dragPose(PART_START, 100, 0).yaw, PART_START.yaw + 1);
});
