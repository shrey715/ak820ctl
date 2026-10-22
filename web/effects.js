// Effect previews, pattern fills and the music renderer, ported from
// ak820/effects.py, ak820/patterns.py and ak820/music.py.
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

export function previewFrame({ mode, brightness, speed, direction, color }, t, custom = {}) {
  if (mode === DATA.customMode) {
    const b = brightnessScale(brightness);
    return Object.fromEntries(Object.entries(custom).map(([led, rgb]) =>
      [led, rgb.map((c) => Math.round(c * b))]));
  }
  const m = MODES[mode];
  if (!m || mode === 22 || mode === 23) return {};
  const A = DATA.attr;
  const sp = m.attr & A.speed ? 0.25 + 0.3 * (speed - 1) : 0.5;
  const fixed = m.attr & A.color && color !== DATA.rainbow
    ? DATA.palette[color].rgb.map((c) => c / 255) : null;
  const left = Boolean(m.attr & A.direction) && direction === 1;
  const bscale = m.attr & A.brightness ? brightnessScale(brightness) : 1;
  const out = {};
  for (const [ledStr, [u, v, row]] of Object.entries(POS)) {
    const led = Number(ledStr);
    const uu = left ? 1 - u : u;
    let hue = null, k = 1;
    switch (mode) {
      case 1: k = (0.5 + 0.5 * Math.sin(2 * Math.PI * (uu * 1.6 - t * sp))) ** 2; hue = u * 0.8 + t * 0.05; break;
      case 2: k = Math.max(0, Math.sin(2 * Math.PI * (t * sp * 0.6 + rand(led)))) ** 10; hue = rand(led, 1); break;
      case 3: { const vv = left ? 1 - v : v; k = (0.5 + 0.5 * Math.sin(2 * Math.PI * (vv * 1.4 - t * sp))) ** 2; hue = v * 0.8 + t * 0.05; break; }
      case 4: { const d = Math.abs(u - 0.5) * 2; k = (0.5 + 0.5 * Math.sin(2 * Math.PI * (d * 1.5 - t * sp))) ** 2; hue = d * 0.7 + t * 0.05; break; }
      case 5: hue = t * sp * 0.15; break;
      case 6: { const a = Math.atan2((v - 0.5) * 0.4, u - 0.5) / (2 * Math.PI); hue = a + Math.hypot(u - 0.5, v - 0.5) - t * sp * 0.25; k = 0.6 + 0.4 * Math.sin(2 * Math.PI * (a * 3 + t * sp * 0.5)); break; }
      case 7: hue = u * 0.85; break;
      case 8: k = 0.5 - 0.5 * Math.cos(2 * Math.PI * t * sp * 0.4); hue = t * 0.03; break;
      case 9: { const p = (t * sp * 0.5) % 1; k = Math.max(clamp(1 - Math.abs(uu - p) * 7), clamp(1 - Math.abs(v - p) * 5)); hue = p + u * 0.3; break; }
      case 11: k = (0.5 - 0.5 * Math.cos(2 * Math.PI * (t * sp * 0.4 + rand(led)))) ** 2; hue = rand(led, 2); break;
      case 12: hue = uu * 0.7 + v * 0.3 - t * sp * 0.25; if (fixed) k = 0.5 + 0.5 * Math.sin(2 * Math.PI * (uu + v * 0.5 - t * sp * 0.5)); break;
      case 15: { const ph = 0.5 + 0.5 * Math.sin(2 * Math.PI * t * sp * 0.4); k = row < 3 ? ph : 1 - ph; hue = row < 3 ? 0 : 0.6; break; }
      case 16: { const col = Math.round(u * 15); const pos = ((t * sp * 0.6 + rand(col, 3)) % 1.4) - 0.2; k = v <= pos + 0.1 ? clamp(1 - (pos - v) * 3) * clamp(1 + (pos - v) * 12) : 0; hue = rand(col, 4); break; }
      case 17: { const a = Math.atan2((v - 0.5) * 0.4, u - 0.5); k = (0.5 + 0.5 * Math.cos(4 * a - t * sp * 3)) ** 3; hue = a / (2 * Math.PI) + t * 0.05; break; }
      case 18: { const y = 0.5 + 0.4 * Math.sin(2 * Math.PI * (uu - t * sp * 0.4)); k = clamp(1 - Math.abs(v - y) * 4); hue = uu; break; }
      case 19: { const p = ((t * sp * 0.45) % 1.2) - 0.1; k = clamp(1 - Math.abs(uu - p) * 6); hue = p; break; }
    }
    const rgb = fixed ?? hsv(hue ?? u);
    const f = clamp(k) * bscale;
    out[led] = rgb.map((c) => Math.round(c * 255 * f));
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
