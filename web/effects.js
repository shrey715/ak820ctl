// Effect previews, pattern fills and the music renderer, ported from
// openajazz/effects.py, openajazz/patterns.py and openajazz/music.py.
// Effect formulas adapted from prasoondev/ajazz-linux (MIT, (c) 2026 prasoon).
import { DATA } from "./data.js";

const xs = DATA.keys.map((k) => k.rect[0] + k.rect[2] / 2);
const ys = DATA.keys.map((k) => k.rect[1] + k.rect[3] / 2);
const X0 = Math.min(...xs), X1 = Math.max(...xs), Y0 = Math.min(...ys), Y1 = Math.max(...ys);
// led -> [u (0 left..1 right), v (0 top..1 bottom), row]
export const POS = Object.fromEntries(DATA.keys.map((k, i) =>
  [k.led, [(xs[i] - X0) / (X1 - X0), (ys[i] - Y0) / (Y1 - Y0), k.row]]));
const MODES = Object.fromEntries(DATA.modes.map((m) => [m.mode, m]));

const clamp = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

export function hsv(h, s = 1, v = 1) {
  h = ((h % 1) + 1) % 1;
  const i = Math.floor(h * 6), f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i % 6];
  return [r, g, b];
}

function rand(n, salt = 0) {
  let h = (Math.imul(n, 2654435761) + Math.imul(salt, 40503)) >>> 0;
  h ^= h >>> 15;
  h = Math.imul(h, 2246822519) >>> 0;
  h ^= h >>> 13;
  return (h & 0xffff) / 0xffff;
}

const brightnessScale = (level) => 0.18 + 0.82 * (level - 1) / 4;

// Effects that react to typing. Previews feed them simulated key presses, plus
// keys you click on the board.
export const REACTIVE = new Set([4, 12]);
const PRESS_EVERY = 0.9;
const LEDS = Object.keys(POS).map(Number).sort((a, b) => a - b);

export function autoPresses(t, keep = 3) {
  const slot = Math.floor(t / PRESS_EVERY), out = [];
  for (let s = Math.max(0, slot - keep + 1); s <= slot; s++)
    out.push([LEDS[Math.floor(rand(s, 7) * LEDS.length) % LEDS.length], s * PRESS_EVERY]);
  return out;
}

function pressWave(u, row, t, sp, presses, sameRow) {
  let best = 0, hue = 0;
  for (const [led, pt] of presses) {
    const age = t - pt;
    if (age < 0 || age >= 2.2 || !POS[led]) continue;
    const [pu, , prow] = POS[led];
    if (sameRow && prow !== row) continue;
    const front = age * (0.35 + 0.25 * sp);
    const k = clamp(1 - Math.abs(Math.abs(u - pu) - front) * 9) * (1 - age / 2.2);
    if (k > best) { best = k; hue = pu + age * 0.15; }
  }
  return [best, hue];
}

export function previewFrame({ mode, brightness, speed, direction, color }, t, custom = {}, presses = []) {
  if (mode === DATA.customMode) {
    const b = brightnessScale(brightness);
    return Object.fromEntries(Object.entries(custom).map(([led, rgb]) =>
      [led, rgb.map((c) => Math.floor(c * b))]));
  }
  const m = MODES[mode];
  if (!m || mode === 22 || mode === 23) return {};
  const A = DATA.attr;
  const sp = m.attr & A.speed ? 0.25 + 0.3 * (speed - 1) : 0.5;
  const fixed = m.attr & A.color && color !== DATA.rainbow
    ? DATA.palette[color].rgb.map((c) => c / 255) : null;
  const rev = Boolean(m.attr & A.direction) && direction === 1;
  const bscale = m.attr & A.brightness ? brightnessScale(brightness) : 1;
  if (REACTIVE.has(mode)) presses = [...presses, ...autoPresses(t)];
  const out = {};
  for (const [ledStr, [u, v, row]] of Object.entries(POS)) {
    const led = Number(ledStr);
    const uu = rev ? 1 - u : u;
    let hue = null, k = 1;
    switch (mode) {
      case 1: k = (0.5 + 0.5 * Math.sin(2 * Math.PI * (uu * 1.6 - t * sp))) ** 2; hue = u * 0.8 + t * 0.05; break;
      case 2: k = Math.max(0, Math.sin(2 * Math.PI * (t * sp * 0.6 + rand(led)))) ** 10; hue = rand(led, 1); break;
      case 3: { const vv = rev ? 1 - v : v; k = (0.5 + 0.5 * Math.sin(2 * Math.PI * (vv * 1.4 - t * sp))) ** 2; hue = v * 0.8 + t * 0.05; break; }
      case 4: [k, hue] = pressWave(u, row, t, sp, presses, true); break;  // bidirectional ejection, per row
      case 5: hue = t * sp * 0.15; break;
      case 6: {  // kaleidoscope: rings from the centre outwards
        const r = Math.hypot(u - 0.5, (v - 0.5) * 0.42) * 2;
        k = (0.5 + 0.5 * Math.sin(2 * Math.PI * (r * 1.8 + (rev ? t : -t) * sp))) ** 2;
        hue = r * 0.6 - t * 0.05; break;
      }
      case 7: hue = u * 0.85; break;
      case 8: k = 0.5 - 0.5 * Math.cos(2 * Math.PI * t * sp * 0.4); hue = t * 0.03; break;
      case 9: {  // cross operation: waves from both edges pass each other
        const p = ((t * sp * 0.45) % 1.4) - 0.2;
        const kl = clamp(1 - Math.abs(u - p) * 7), kr = clamp(1 - Math.abs(u - (1 - p)) * 7);
        k = Math.max(kl, kr); hue = (kl >= kr ? 0 : 0.55) + t * 0.03; break;
      }
      case 11: k = (0.5 - 0.5 * Math.cos(2 * Math.PI * (t * sp * 0.4 + rand(led)))) ** 2; hue = rand(led, 2); break;
      case 12: [k, hue] = pressWave(u, row, t, sp, presses, false); break;  // jiangshan, whole column
      case 15: {  // top three rows sweep right, bottom three sweep left
        const p = ((t * sp * 0.4) % 1.5) - 0.25, c = row < 3 ? p : 1 - p;
        k = clamp(1 - Math.max(0, Math.abs(u - c) - 0.12) * 10); hue = (row < 3 ? 0 : 0.6) + t * 0.02; break;
      }
      case 16: {  // sideways rain
        k = 0;
        for (let j = 0; j < 2; j++) {
          const x = ((t * sp * 0.55 + rand(row * 3 + j, 11) * 1.4) % 1.4) - 0.2, d = x - uu;
          if (d >= -0.03) {
            const kk = clamp(1 - d * 5) * clamp(1 + d * 30);
            if (kk > k) { k = kk; hue = rand(row * 3 + j, 12); }
          }
        }
        break;
      }
      case 17: { const a = Math.atan2((v - 0.5) * 0.4, u - 0.5); k = (0.5 + 0.5 * Math.cos(4 * a - t * sp * 3)) ** 3; hue = a / (2 * Math.PI) + t * 0.05; break; }
      case 18: { const y = 0.5 + 0.4 * Math.sin(2 * Math.PI * (uu - t * sp * 0.4)); k = clamp(1 - Math.abs(v - y) * 4); hue = uu; break; }
      case 19: {  // galloping horse: one row at a time, left to right
        const cycle = (t * sp * 0.6) % 6, cur = Math.floor(cycle), prog = (cycle % 1) * 1.25;
        k = row === cur && uu <= prog ? clamp(1 - (prog - uu) * 3) : 0; hue = row / 6 + t * 0.02; break;
      }
    }
    const rgb = fixed ?? hsv(hue ?? u);
    const f = clamp(k) * bscale;
    out[led] = rgb.map((c) => Math.floor(c * 255 * f));  // truncate like the Python side
  }
  return out;
}

// -- pattern fills ---------------------------------------------------------
const mix = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
const to255 = (rgb) => rgb.map((c) => Math.round(c * 255));
const WASD = ["w", "a", "s", "d", "up", "down", "left", "right"].map((k) => DATA.hid[k]);

export function pattern(name, primary, secondary) {
  const out = {};
  for (const k of DATA.keys) {
    const [x, y] = POS[k.led];
    out[k.led] = {
      "rainbow-horizontal": () => to255(hsv(x * 0.85)),
      "rainbow-vertical": () => to255(hsv(y * 0.75)),
      "rainbow-diagonal": () => to255(hsv((x + y * 0.5) * 0.6)),
      "gradient-horizontal": () => mix(primary, secondary, x),
      "gradient-vertical": () => mix(primary, secondary, y),
      "highlight-gaming": () => (WASD.includes(k.code) ? primary : secondary),
      random: () => to255(hsv(Math.random())),
    }[name]?.() ?? primary;
  }
  return out;
}

// -- music -----------------------------------------------------------------
export const BANDS = 16;

export class Analyzer {
  constructor(analyserNode, sampleRate, sensitivity = 1) {
    this.node = analyserNode;
    this.sensitivity = sensitivity;
    this.spec = new Float32Array(analyserNode.frequencyBinCount);
    const binHz = sampleRate / analyserNode.fftSize;
    const edges = Array.from({ length: BANDS + 1 }, (_, i) => 40 * (16000 / 40) ** (i / BANDS));
    this.bins = edges.slice(0, -1).map((lo, i) => {
      const a = Math.round(lo / binHz);
      return [a, Math.max(Math.round(edges[i + 1] / binHz), a + 1)];
    });
    this.tilt = edges.slice(0, -1).map((lo, i) => 10 * Math.log10(Math.sqrt(lo * edges[i + 1]) / 1000) * 0.5);
    this.levels = new Float32Array(BANDS);
    this.peak = -30;
    this.bass = 0;
  }

  update() {
    this.node.getFloatFrequencyData(this.spec);  // dBFS per bin
    const db = this.bins.map(([a, b], i) => {
      let m = -Infinity;
      for (let j = a; j < b && j < this.spec.length; j++) m = Math.max(m, this.spec[j]);
      return m + this.tilt[i];
    });
    const top = Math.max(...db);
    this.peak = Math.max(top, this.peak - 0.15, -60);
    const span = 40 / this.sensitivity;
    for (let i = 0; i < BANDS; i++) {
      const lv = top < -90 ? 0 : clamp((db[i] - (this.peak - span)) / span);
      this.levels[i] = Math.max(lv, this.levels[i] * 0.82);
    }
    this.bass = Math.max(Math.max(...this.levels.slice(0, 3)), this.bass * 0.85);
  }
}

export class MusicRenderer {
  constructor(style = "spectrum", color = null) {
    this.style = style; this.color = color;
    this.history = new Array(32).fill(0);
    this.t0 = performance.now();
  }

  tint(hue, value) {
    value = clamp(value);
    if (!this.color) return to255(hsv(hue, 1, value));
    return this.color.map((c) => Math.round(c * value));
  }

  frame(levels, bass) {
    const t = (performance.now() - this.t0) / 1000;
    if (this.style === "wave") this.history = [bass, ...this.history.slice(0, -1)];
    const out = {};
    for (const [led, [u, v]] of Object.entries(POS)) {
      if (this.style === "spectrum") {
        const height = levels[Math.min(BANDS - 1, Math.floor(u * BANDS))];
        const fill = 1 - v;
        const on = clamp((height * 1.15 - fill) * 6 + 1);
        out[led] = on ? this.tint(0.33 * (1 - fill), 0.04 + 0.96 * on) : [0, 0, 0];
      } else if (this.style === "pulse") {
        out[led] = this.tint(t * 0.05 + u * 0.3, 0.08 + 0.92 * bass ** 1.5);
      } else {
        const r = Math.hypot(u - 0.5, (v - 0.5) * 0.45);
        const e = this.history[Math.min(this.history.length - 1, Math.floor(r * 2 * this.history.length))];
        out[led] = this.tint(t * 0.04 + r, 0.05 + 0.95 * e ** 1.3);
      }
    }
    return out;
  }
}
