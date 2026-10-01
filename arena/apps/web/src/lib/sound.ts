import { settings } from './settings.js';

/** Lightweight, original WebAudio effects for the card table. No external audio files are needed. */
export type Sfx = 'card' | 'deal' | 'draw' | 'take' | 'discard' | 'transfer' | 'pass' | 'timeout' | 'turn' | 'tick' | 'win' | 'lose' | 'emoji' | 'error';

let ctx: AudioContext | null = null;
let master: GainNode | null = null;

function audio(): AudioContext | null {
  if (!settings.get().sound) return null;
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
    master = ctx.createGain();
    master.connect(ctx.destination);
  }
  if (ctx.state === 'suspended') void ctx.resume();
  if (master) master.gain.value = settings.get().volume;
  return ctx;
}

function out(ac: AudioContext): AudioNode {
  return master ?? ac.destination;
}

/** Call from any tap handler once, so later sounds are allowed to play on iOS WebViews. */
export function unlockAudio(): void {
  audio();
}

function tone(
  ac: AudioContext,
  freq: number,
  start: number,
  duration: number,
  type: OscillatorType = 'sine',
  gain = 0.08,
  endFreq?: number,
): void {
  const osc = ac.createOscillator();
  const envelope = ac.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(Math.max(1, freq), start);
  if (endFreq !== undefined) osc.frequency.exponentialRampToValueAtTime(Math.max(1, endFreq), start + duration);
  envelope.gain.setValueAtTime(0.0001, start);
  envelope.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain), start + Math.min(0.012, duration * 0.25));
  envelope.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(envelope).connect(out(ac));
  osc.start(start);
  osc.stop(start + duration + 0.025);
}

function noise(ac: AudioContext, start: number, duration: number, freq: number, gain = 0.08, endFreq?: number): void {
  const length = Math.max(1, Math.floor(ac.sampleRate * duration));
  const buffer = ac.createBuffer(1, length, ac.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) {
    const envelope = (1 - i / length) ** 2;
    data[i] = (Math.random() * 2 - 1) * envelope;
  }
  const source = ac.createBufferSource();
  source.buffer = buffer;
  const filter = ac.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.setValueAtTime(freq, start);
  if (endFreq !== undefined) filter.frequency.exponentialRampToValueAtTime(Math.max(100, endFreq), start + duration);
  const volume = ac.createGain();
  volume.gain.value = gain;
  source.connect(filter).connect(volume).connect(out(ac));
  source.start(start);
}

export function play(sfx: Sfx): void {
  const ac = audio();
  if (!ac) return;
  const t = ac.currentTime;
  const variation = 0.94 + Math.random() * 0.12;

  switch (sfx) {
    case 'card':
      // A soft, papery flick with a tiny wooden tap.
      noise(ac, t, 0.075, 3600 * variation, 0.095, 1250);
      tone(ac, 210 + Math.random() * 35, t + 0.008, 0.045, 'triangle', 0.025, 145);
      break;
    case 'deal':
      // A quick, uneven sequence, like cards being dealt onto felt.
      for (let i = 0; i < 4; i++) {
        const at = t + i * 0.072;
        noise(ac, at, 0.055, 3200 - i * 180, 0.07, 1200);
        tone(ac, 175 + i * 13, at + 0.006, 0.035, 'triangle', 0.018, 130);
      }
      break;
    case 'draw':
      noise(ac, t, 0.11, 2600, 0.075, 900);
      tone(ac, 430, t + 0.015, 0.09, 'sine', 0.035, 590);
      break;
    case 'take':
      // Low, soft gathering sound instead of a harsh buzz.
      noise(ac, t, 0.24, 950, 0.13, 300);
      tone(ac, 245, t + 0.025, 0.18, 'triangle', 0.045, 165);
      break;
    case 'discard':
      noise(ac, t, 0.13, 1700, 0.08, 600);
      tone(ac, 330, t + 0.015, 0.1, 'triangle', 0.035, 220);
      break;
    case 'transfer':
      noise(ac, t, 0.13, 2300, 0.07, 650);
      tone(ac, 520, t + 0.035, 0.12, 'sine', 0.045, 780);
      break;
    case 'pass':
      tone(ac, 660, t, 0.075, 'sine', 0.045, 520);
      tone(ac, 440, t + 0.075, 0.09, 'sine', 0.035, 390);
      break;
    case 'timeout':
      // Noticeable but mellow double chime.
      tone(ac, 740, t, 0.16, 'sine', 0.07, 620);
      tone(ac, 554, t + 0.16, 0.22, 'sine', 0.065, 440);
      break;
    case 'turn':
      tone(ac, 587.33, t, 0.19, 'sine', 0.055, 660);
      tone(ac, 880, t + 0.085, 0.24, 'sine', 0.065, 1046.5);
      break;
    case 'tick':
      tone(ac, 1250, t, 0.035, 'sine', 0.022, 1050);
      break;
    case 'win':
      // Bright, warm major arpeggio.
      [523.25, 659.25, 783.99, 1046.5, 1318.5].forEach((f, i) => {
        tone(ac, f, t + i * 0.095, 0.28, 'sine', i === 4 ? 0.085 : 0.065, f * 1.012);
      });
      break;
    case 'lose':
      // Gentle descending notes, without the abrasive sawtooth timbre.
      [392, 329.63, 261.63].forEach((f, i) => tone(ac, f, t + i * 0.14, 0.24, 'triangle', 0.045, f * 0.985));
      break;
    case 'emoji':
      tone(ac, 740, t, 0.085, 'sine', 0.055, 990);
      tone(ac, 990, t + 0.045, 0.1, 'sine', 0.04, 1180);
      break;
    case 'error':
      tone(ac, 260, t, 0.11, 'triangle', 0.05, 205);
      tone(ac, 205, t + 0.12, 0.13, 'triangle', 0.04, 170);
      break;
  }
}
