// Desktop overlay scenes. Run: npm test (node --test, TS stripped by Node).
import { test } from "node:test";
import assert from "node:assert/strict";

const { sceneFor, MusicNotice } = await import("../src/desktop.ts");

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
