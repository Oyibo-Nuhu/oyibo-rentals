// Engine sounds made with the Web Audio API: no audio files, nothing to download or license.
// vroom(): idle → rev blip → launch roar that fades as the car leaves (timed to the login animation).
const KEY = "oy-sound";
let ctx = null;

function audio() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

function noiseBuffer(ac, seconds = 3) {
  const buf = ac.createBuffer(1, ac.sampleRate * seconds, ac.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return buf;
}

function distortion(ac, amount = 18) {
  const ws = ac.createWaveShaper(), n = 1024, curve = new Float32Array(n);
  for (let i = 0; i < n; i++) { const x = (i * 2) / n - 1; curve[i] = ((3 + amount) * x * 20 * Math.PI / 180) / (Math.PI + amount * Math.abs(x)); }
  ws.curve = curve; ws.oversample = "2x";
  return ws;
}

/**
 * Engine voice. `rpm` is a list of [time, frequencyHz] points; `vol` a list of [time, gain].
 * Two detuned saws + a sub square through a distorting low-pass, pulsed like cylinders firing, plus exhaust hiss.
 */
function engine(ac, t0, rpm, vol) {
  const out = ac.createGain(); out.gain.value = 0;
  const comp = ac.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 6;
  out.connect(comp).connect(ac.destination);

  const filter = ac.createBiquadFilter(); filter.type = "lowpass"; filter.Q.value = 6;
  const shaper = distortion(ac, 26);
  const pulse = ac.createGain(); pulse.gain.value = 0.6;
  filter.connect(shaper).connect(pulse).connect(out);

  const oscs = [["sawtooth", 1, 0], ["sawtooth", 2.01, 7], ["square", 0.5, -5]].map(([type, mult, detune]) => {
    const o = ac.createOscillator(); o.type = type; o.detune.value = detune;
    const g = ac.createGain(); g.gain.value = type === "square" ? 0.35 : 0.5;
    o.connect(g).connect(filter);
    return { o, mult };
  });
  const lfo = ac.createOscillator(); lfo.type = "square";      // cylinder "chug"
  const lfoGain = ac.createGain(); lfoGain.gain.value = 0.35;
  lfo.connect(lfoGain).connect(pulse.gain);

  const hiss = ac.createBufferSource(); hiss.buffer = noiseBuffer(ac);
  const band = ac.createBiquadFilter(); band.type = "bandpass"; band.Q.value = 0.9;
  const hissGain = ac.createGain(); hissGain.gain.value = 0;
  hiss.connect(band).connect(hissGain).connect(out);

  const end = t0 + rpm[rpm.length - 1][0];
  const [, f0] = rpm[0];
  oscs.forEach(({ o, mult }) => o.frequency.setValueAtTime(f0 * mult, t0));
  lfo.frequency.setValueAtTime(f0 / 2, t0);
  filter.frequency.setValueAtTime(f0 * 6, t0);
  band.frequency.setValueAtTime(f0 * 9, t0);
  for (const [t, f] of rpm.slice(1)) {
    oscs.forEach(({ o, mult }) => o.frequency.exponentialRampToValueAtTime(f * mult, t0 + t));
    lfo.frequency.exponentialRampToValueAtTime(f / 2, t0 + t);
    filter.frequency.exponentialRampToValueAtTime(Math.min(9000, f * 7), t0 + t);
    band.frequency.exponentialRampToValueAtTime(Math.min(9000, f * 10), t0 + t);
  }
  out.gain.setValueAtTime(0.0001, t0);
  hissGain.gain.setValueAtTime(0.0001, t0);
  for (const [t, g] of vol) {
    out.gain.linearRampToValueAtTime(g, t0 + t);
    hissGain.gain.linearRampToValueAtTime(g * 0.12, t0 + t);
  }
  [...oscs.map((x) => x.o), lfo, hiss].forEach((n) => { n.start(t0); n.stop(end + 0.05); });
}

export const sound = {
  get enabled() { try { return localStorage.getItem(KEY) !== "off"; } catch { return true; } },
  toggle() { try { localStorage.setItem(KEY, this.enabled ? "off" : "on"); } catch {} },

  /** The login launch: idle while Zuma rolls in, a rev, then a roar as it zooms off. `delay` in seconds. */
  vroom(delay = 0.5) {
    if (!this.enabled) return;
    const ac = audio(); if (!ac) return;
    const t0 = ac.currentTime + delay;
    engine(ac, t0,
      [[0, 48], [0.7, 52], [0.85, 130], [1.15, 70], [1.3, 72], [1.45, 150], [1.65, 82], [1.9, 110], [2.5, 290], [2.75, 230], [3.1, 170]],
      [[0.15, 0.22], [0.7, 0.22], [0.85, 0.5], [1.15, 0.3], [1.45, 0.55], [1.65, 0.32], [1.9, 0.55], [2.4, 0.75], [2.75, 0.4], [3.1, 0.0001]]);
  },

  /** A short drive-in for the payment celebration. */
  driveIn(delay = 0.15) {
    if (!this.enabled) return;
    const ac = audio(); if (!ac) return;
    const t0 = ac.currentTime + delay;
    engine(ac, t0, [[0, 160], [0.9, 220], [1.4, 70], [1.9, 60], [2.2, 140], [2.5, 75], [2.9, 55]],
      [[0.1, 0.45], [0.9, 0.55], [1.4, 0.25], [2.0, 0.2], [2.2, 0.45], [2.5, 0.22], [2.9, 0.0001]]);
  },

  /** Two quick tones for a speeding warning. */
  alert() {
    if (!this.enabled) return;
    const ac = audio(); if (!ac) return;
    [0, 0.18].forEach((d, i) => {
      const o = ac.createOscillator(), g = ac.createGain();
      o.type = "triangle"; o.frequency.value = i ? 660 : 880;
      g.gain.setValueAtTime(0.0001, ac.currentTime + d);
      g.gain.exponentialRampToValueAtTime(0.25, ac.currentTime + d + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + d + 0.16);
      o.connect(g).connect(ac.destination); o.start(ac.currentTime + d); o.stop(ac.currentTime + d + 0.2);
    });
  },

  /** A tiny confirmation click when sound is switched on. */
  blip() {
    const ac = audio(); if (!ac) return;
    const o = ac.createOscillator(), g = ac.createGain();
    o.type = "sine"; o.frequency.setValueAtTime(520, ac.currentTime); o.frequency.exponentialRampToValueAtTime(880, ac.currentTime + 0.08);
    g.gain.setValueAtTime(0.18, ac.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + 0.12);
    o.connect(g).connect(ac.destination); o.start(); o.stop(ac.currentTime + 0.13);
  },

  /** Call from a click so browsers allow audio later in the same visit. */
  unlock() { if (this.enabled) audio(); },
};
