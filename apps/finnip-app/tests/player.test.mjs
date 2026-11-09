// Player regression checks with a fake Web Audio API. Run: npm test (node --test, TS stripped by Node).
import { test } from "node:test";
import assert from "node:assert/strict";

const started = [];
class FakeSource {
  connect() {}
  start() { started.push(this.buffer); }
  stop() {}
  end() { this.onended?.(); }
}
globalThis.AudioContext = class {
  currentTime = 0;
  destination = {};
  createAnalyser() { return { connect() {}, fftSize: 0 }; }
  createBufferSource() { return (this.last = new FakeSource()); }
  // Decoding resolves only when the test says so, to control the race.
  decodeAudioData(mp3) { return new Promise((resolve) => (this.pending = () => resolve(mp3.name))); }
  resume() { return Promise.resolve(); }
  suspend() { return Promise.resolve(); }
};
const { Player } = await import("../src/player.ts");

test('"done" before the last chunk decodes: plays it, then goes idle', async () => {
  const p = new Player();
  let idle = 0;
  p.onIdle = () => idle++;
  const decoded = p.enqueue(0, { name: "hecho" });
  p.endOfReply(); // the server's "done" right behind the audio
  p.ctx.pending();
  await decoded;
  assert.equal(p.isSpeaking, true);
  assert.deepEqual(started.splice(0), ["hecho"]);
  p.ctx.last.end();
  assert.equal(p.isSpeaking, false);
  assert.equal(idle, 1);
});

test("a chunk still decoding when the reply is flushed is dropped", async () => {
  const p = new Player();
  const decoded = p.enqueue(0, { name: "viejo" });
  p.flush();
  p.ctx.pending();
  await decoded;
  assert.equal(p.isSpeaking, false);
  assert.deepEqual(started.splice(0), []);
});
