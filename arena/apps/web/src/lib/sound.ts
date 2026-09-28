import { settings } from './settings.js';

/**
 * Tiny synthesised sound effects: no audio files to download, instant on slow networks.
 * The AudioContext is created on the first user gesture (required by iOS WebViews).
 */
export type Sfx = 'card' | 'deal' | 'take' | 'discard' | 'turn' | 'tick' | 'win' | 'lose' | 'emoji' | 'error';

let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  if (!settings.get().sound) return null;
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
  }
  if (ctx.state === 'suspended') void ctx.resume();
  return ctx;
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
  osc.connect(g).connect(ac.destination);
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
  src.connect(filter).connect(g).connect(ac.destination);
  src.start(start);
}

export function play(sfx: Sfx): void {
  const ac = audio();
  if (!ac) return;
  const t = ac.currentTime;
  switch (sfx) {
    case 'card':
      noise(ac, t, 0.07, 2400);
      break;
    case 'deal':
      for (let i = 0; i < 4; i++) noise(ac, t + i * 0.06, 0.05, 2800, 0.18);
      break;
    case 'take':
      noise(ac, t, 0.25, 700, 0.3);
      break;
    case 'discard':
      noise(ac, t, 0.18, 1400, 0.22);
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
