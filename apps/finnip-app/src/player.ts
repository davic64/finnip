// Plays reply chunks in seq order on its own AudioContext; suspend/resume gives an exact pause for barge-in.
export class Player {
  private ctx = new AudioContext();
  private queue = new Map<number, AudioBuffer>();
  private nextSeq = 0;
  private source: AudioBufferSourceNode | null = null;
  private startedAt = 0;
  private replyDone = false;
  private speaking = false;
  readonly analyser = this.ctx.createAnalyser();
  onStart = () => {};
  onIdle = () => {};

  constructor() {
    this.analyser.fftSize = 256;
    this.analyser.connect(this.ctx.destination);
  }

  /** iOS only lets audio start inside a user gesture. */
  unlock() {
    return this.ctx.resume();
  }

  get isSpeaking() {
    return this.speaking;
  }

  async enqueue(seq: number, mp3: ArrayBuffer) {
    const buffer = await this.ctx.decodeAudioData(mp3);
    if (seq < this.nextSeq) return; // flushed while decoding
    this.queue.set(seq, buffer);
    if (!this.source) this.playNext();
  }

  /** Short soft two-note chime: instant feedback that the phrase was heard, before any reply. */
  chime() {
    const t0 = this.ctx.currentTime;
    const gain = this.ctx.createGain();
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.06, t0 + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.22);
    gain.connect(this.ctx.destination);
    [880, 1320].forEach((freq, i) => {
      const osc = this.ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = freq;
      osc.connect(gain);
      osc.start(t0 + i * 0.07);
      osc.stop(t0 + 0.22);
    });
  }

  /** Server sent "done": finish once the queue drains. */
  endOfReply() {
    this.replyDone = true;
    if (!this.source && this.queue.size === 0) this.finish();
  }

  private playNext() {
    const buffer = this.queue.get(this.nextSeq);
    if (!buffer) {
      this.source = null;
      if (this.replyDone) this.finish();
      return; // waiting for the next chunk
    }
    if (!this.speaking) {
      this.speaking = true;
      this.onStart();
    }
    this.queue.delete(this.nextSeq++);
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.analyser);
    src.onended = () => {
      if (this.source === src) this.playNext();
    };
    this.source = src;
    this.startedAt = this.ctx.currentTime;
    src.start();
  }

  private finish() {
    const was = this.speaking;
    this.nextSeq = 0;
    this.replyDone = false;
    this.speaking = false;
    if (was) this.onIdle();
  }

  /** What the user heard: the chunk playing now (seq) and how far into it. */
  played() {
    if (!this.source) return { played_seq: this.nextSeq, played_ms: 0 };
    return { played_seq: this.nextSeq - 1, played_ms: Math.round((this.ctx.currentTime - this.startedAt) * 1000) };
  }

  pause() {
    return this.ctx.suspend();
  }

  resume() {
    return this.ctx.resume();
  }

  /** Stop now and drop everything queued. */
  flush() {
    const src = this.source;
    this.source = null;
    src?.stop();
    this.queue.clear();
    void this.ctx.resume();
    this.finish();
  }
}
