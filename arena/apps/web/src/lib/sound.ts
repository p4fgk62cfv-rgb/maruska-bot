import { settings } from './settings.js';

/**
 * Game sounds: short recorded-style effects from /sfx (≈80 KB in all), decoded once and played
 * through WebAudio so they overlap and start instantly. Until a file is loaded the tiny synth
 * below stands in. The AudioContext is created on the first touch (required by iOS WebViews).
 */
export type Sfx = 'card' | 'deal' | 'draw' | 'take' | 'discard' | 'transfer' | 'pass' | 'timeout' | 'turn' | 'tick' | 'win' | 'lose' | 'emoji' | 'error';

const FILES: Sfx[] = ['card', 'deal', 'draw', 'take', 'discard', 'transfer', 'pass', 'timeout', 'turn', 'tick', 'win', 'lose', 'emoji', 'error'];

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
const buffers = new Map<Sfx, AudioBuffer>();
let loading = false;

function load(ac: AudioContext): void {
  if (loading) return;
  loading = true;
  for (const name of FILES) {
    fetch(`/sfx/${name}.mp3`)
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(String(r.status)))))
      // Old Safari only has the callback form of decodeAudioData.
      .then((data) => new Promise<AudioBuffer>((resolve, reject) => ac.decodeAudioData(data, resolve, reject)))
      .then((buffer) => buffers.set(name, buffer))
      .catch(() => undefined);
  }
}

function audio(): AudioContext | null {
  if (!settings.get().sound) return null;
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
    master = ctx.createGain();
    master.connect(ctx.destination);
    load(ctx);
  }
  if (ctx.state === 'suspended') void ctx.resume();
  if (master) master.gain.value = settings.get().volume;
  return ctx;
}

function out(ac: AudioContext): AudioNode {
  return master ?? ac.destination;
}

/** Call from any tap handler once, so later sounds are allowed to play. */
export function unlockAudio(): void {
  audio();
}

function tone(ac: AudioContext, freq: number, start: number, duration: number, type: OscillatorType = 'sine', gain = 0.12): void {
  const osc = ac.createOscillator();
  const g = ac.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  g.gain.setValueAtTime(0, start);
  g.gain.linearRampToValueAtTime(gain, start + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(g).connect(out(ac));
  osc.start(start);
  osc.stop(start + duration + 0.02);
}

function noise(ac: AudioContext, start: number, duration: number, freq: number, gain = 0.25): void {
  const length = Math.max(1, Math.floor(ac.sampleRate * duration));
  const buffer = ac.createBuffer(1, length, ac.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / length) ** 2;
  const src = ac.createBufferSource();
  src.buffer = buffer;
  const filter = ac.createBiquadFilter();
  filter.type = 'bandpass';
  filter.frequency.value = freq;
  const g = ac.createGain();
  g.gain.value = gain;
  src.connect(filter).connect(g).connect(out(ac));
  src.start(start);
}

export function play(sfx: Sfx): void {
  const ac = audio();
  if (!ac) return;
  const buffer = buffers.get(sfx);
  if (buffer) {
    const src = ac.createBufferSource();
    src.buffer = buffer;
    // A touch of pitch variety so a run of cards does not sound like a machine gun.
    if (sfx === 'card' || sfx === 'draw') src.playbackRate.value = 0.94 + Math.random() * 0.12;
    src.connect(out(ac));
    src.start();
    return;
  }
  const t = ac.currentTime;
  switch (sfx) {
    case 'card':
      noise(ac, t, 0.07, 2400);
      break;
    case 'deal':
      for (let i = 0; i < 4; i++) noise(ac, t + i * 0.06, 0.05, 2800, 0.18);
      break;
    case 'draw':
      noise(ac, t, 0.05, 2800, 0.15);
      break;
    case 'take':
      noise(ac, t, 0.25, 700, 0.3);
      break;
    case 'discard':
      noise(ac, t, 0.18, 1400, 0.22);
      break;
    case 'transfer':
      noise(ac, t, 0.055, 2600, 0.17);
      tone(ac, 740, t + 0.045, 0.11, 'triangle', 0.07);
      break;
    case 'pass':
      tone(ac, 520, t, 0.08, 'sine', 0.055);
      tone(ac, 390, t + 0.06, 0.1, 'sine', 0.045);
      break;
    case 'timeout':
      tone(ac, 880, t, 0.13, 'square', 0.055);
      tone(ac, 660, t + 0.13, 0.18, 'square', 0.055);
      break;
    case 'turn':
      tone(ac, 660, t, 0.18);
      tone(ac, 990, t + 0.09, 0.22);
      break;
    case 'tick':
      tone(ac, 1500, t, 0.05, 'square', 0.04);
      break;
    case 'win':
      [523, 659, 784, 1046].forEach((f, i) => tone(ac, f, t + i * 0.11, 0.35, 'triangle', 0.12));
      break;
    case 'lose':
      [392, 330, 262].forEach((f, i) => tone(ac, f, t + i * 0.16, 0.4, 'sawtooth', 0.05));
      break;
    case 'emoji':
      tone(ac, 880, t, 0.12, 'sine', 0.08);
      break;
    case 'error':
      tone(ac, 180, t, 0.18, 'square', 0.05);
      break;
  }
}
