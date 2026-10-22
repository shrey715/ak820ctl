// WebHID port of openajazz/protocol.py + openajazz/control.py.  See PROTOCOL.md.
import { DATA } from "./data.js";

export const VENDOR_ID = 0x1a2c;
export const PRODUCTS = { 0xa036: "USB (wired)", 0x8fff: "2.4G dongle" };
const MAGIC = [0xaa, 0x55, 0xcc, 0x33];
const LEN = 64, CHUNK = 54, LED_SLOTS = 108;
const CMD = {
  KEY_CHUNK0: 0x00, REMAP: 0x04, LIGHT: 0x07, FACTORY_RESET: 0x08, STREAM_BEGIN: 0x09,
  CUSTOM_BEGIN: 0x0b, SLEEP: 0x0c, RESPONSE: 0x0d, STATUS: 0x0e, RESET_KEYS: 0x0f,
  FN_SWITCH: 0x10, FRAME_BASE: 0xf0, CUSTOM_BASE: 0xf6,
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const hidSupported = () => "hid" in navigator;

// -- keys ------------------------------------------------------------------
export function keyCode(name) {
  const n0 = name.trim().toLowerCase();
  if (n0.startsWith("0x")) return parseInt(n0, 16);
  const n = DATA.aliases[n0] ?? n0;
  if (n === "fn") return DATA.fnCode;
  if (n in DATA.hid) return DATA.hid[n];
  throw new Error(`unknown key '${name}'`);
}
export function targetCode(name) {
  const n = DATA.aliases[name.trim().toLowerCase()] ?? name.trim().toLowerCase();
  return n in DATA.media ? DATA.media[n] : keyCode(name);
}
export function codeName(code) {
  for (const table of [DATA.hid, DATA.media])
    for (const [n, c] of Object.entries(table)) if (c === code) return n;
  return code === DATA.fnCode ? "fn" : "0x" + code.toString(16).padStart(2, "0");
}

// Macro timing byte, mirrors sub_4232d0 (see encode_delay in protocol.py).
export function encodeDelay(release, ms) {
  const d = Math.min(Math.max(ms, 0), 31000);
  let hi = 0, lo = 0, count;
  if (d <= 10) count = 1;
  else if (d <= 310) count = Math.floor(d / 10);
  else if (d <= 1550) { count = Math.floor(d / 50); lo = 1; }
  else if (d <= 3100) { count = Math.floor(d / 100); lo = 1; }
  else { count = Math.floor(d / 1000); hi = 1; lo = 1; }
  return ((release ? 1 : 0) << 7) | (hi << 6) | (lo << 5) | (count & 0x1f);
}

export function parseMacroEvents(text, defaultDelay = 10) {
  const events = [];
  for (const tok of text.trim().split(/\s+/).filter(Boolean)) {
    const [body, delayStr] = tok.split("@");
    const delay = delayStr ? parseInt(delayStr, 10) : defaultDelay;
    if ((body[0] === "+" || body[0] === "-") && body.length > 1) {
      events.push([keyCode(body.slice(1)), body[0] === "-", delay]);
    } else {
      const c = keyCode(body);
      events.push([c, false, defaultDelay], [c, true, delay]);
    }
  }
  return events;
}

// -- transport -------------------------------------------------------------
export class Keyboard {
  constructor(device, { log = () => {}, simulated = false } = {}) {
    this.device = device;
    this.simulated = simulated;
    this.log = log;
    this.replies = [];
    this.waiters = [];
    this.queue = Promise.resolve();
    this.onInput = (e) => this._input(new Uint8Array(e.data.buffer));
  }

  static filters() {
    return [{ vendorId: VENDOR_ID, usagePage: 0xff02, usage: 0x02 }];
  }

  static isControl(device) {
    return device.collections.some((c) => c.usagePage === 0xff02 && c.usage === 0x02);
  }

  static async request(opts) {
    const devices = await navigator.hid.requestDevice({ filters: Keyboard.filters() });
    const dev = devices.find(Keyboard.isControl);
    return dev ? Keyboard.open(dev, opts) : null;
  }

  static async reconnect(opts) {
    if (!hidSupported()) return null;
    const devices = await navigator.hid.getDevices();
    const dev = devices.find((d) => d.vendorId === VENDOR_ID && Keyboard.isControl(d));
    return dev ? Keyboard.open(dev, opts) : null;
  }

  static async open(device, opts) {
    if (!device.opened) await device.open();
    const kb = new Keyboard(device, opts);
    device.addEventListener("inputreport", kb.onInput);
    return kb;
  }

  get name() {
    if (this.simulated) return "simulated keyboard";
    return PRODUCTS[this.device.productId] ?? this.device.productName ?? "keyboard";
  }

  async close() {
    if (this.device) {
      this.device.removeEventListener("inputreport", this.onInput);
      await this.device.close().catch(() => {});
    }
  }

  _input(data) {
    if (data.length < 5 || MAGIC.some((b, i) => data[i] !== b)) return;
    const w = this.waiters.findIndex((x) => x.cmd === data[4]);
    if (w >= 0) this.waiters.splice(w, 1)[0].resolve(data);
  }

  _report(cmd, args = []) {
    const buf = new Uint8Array(LEN);
    buf.set(MAGIC, 0);
    buf[4] = cmd;
    buf.set(args.slice(0, LEN - 5), 5);
    return buf;
  }

  // Writes are serialised; WebHID doesn't like overlapping sendReport calls.
  _locked(fn) {
    const run = this.queue.then(fn, fn);
    this.queue = run.catch(() => {});
    return run;
  }

  async _write(buf) {
    if (!(buf[4] >= 0xf0 && buf[4] <= 0xf5)) {
      let end = buf.length;
      while (end > 5 && buf[end - 1] === 0) end--;
      this.log(Array.from(buf.slice(0, end), (b) => b.toString(16).padStart(2, "0")).join(" "));
    }
    if (this.simulated) return;
    await this.device.sendReport(0, buf);
  }

  send(cmd, args = [], { reply = false, timeout = 500 } = {}) {
    return this._locked(async () => {
      const buf = this._report(cmd, args);
      if (!reply) return this._write(buf);
      const waiting = new Promise((resolve) => {
        const waiter = { cmd, resolve };
        this.waiters.push(waiter);
        setTimeout(() => {
          const i = this.waiters.indexOf(waiter);
          if (i >= 0) { this.waiters.splice(i, 1); resolve(null); }
        }, 100 + timeout);
      });
      await this._write(buf);
      if (this.simulated) return Uint8Array.from([...MAGIC, CMD.STATUS, 87, 2]);
      return waiting;
    });
  }

  _ledBuffer(colors) {
    const buf = new Uint8Array(LED_SLOTS * 3);
    for (const [led, rgb] of Object.entries(colors)) {
      const i = Number(led);
      if (i >= 0 && i < LED_SLOTS) buf.set(rgb, i * 3);
    }
    return buf;
  }

  async _chunks(base, data, count, gapMs) {
    for (let i = 0; i < count; i++) {
      await this.send(base + i, Array.from(data.slice(i * CHUNK, (i + 1) * CHUNK)));
      if (gapMs) await sleep(gapMs);
    }
  }

  // -- commands --------------------------------------------------------------
  async status() {
    const r = await this.send(CMD.STATUS, [], { reply: true });
    if (!r) return null;
    const power = r[6];
    return {
      battery: r[5] <= 100 ? r[5] : null, power,
      powerName: DATA.powerStates[power] ?? `unknown (${power})`,
      online: power !== 0, onCharger: power === 1 || power === 3,
    };
  }

  async setLight(mode, brightness = 5, speed = 4, direction = 0, color = DATA.rainbow) {
    await this.send(CMD.LIGHT, [mode - 1, brightness - 1, speed - 1, direction, color]);
    await sleep(10);
  }

  async setCustomColors(colors, brightness = 5) {
    await this.setLight(DATA.customMode, brightness);
    await this.send(CMD.CUSTOM_BEGIN);
    await sleep(10);
    await this._chunks(CMD.CUSTOM_BASE, this._ledBuffer(colors), 6, 3);
  }

  lightsOff() { return this.setCustomColors({}, 1); }

  async enterLiveMode(mode = DATA.musicMode) {
    await this.setLight(mode, 5, 3);
    await this.send(CMD.STREAM_BEGIN);
    await sleep(50);
  }

  sendFrame(colors) {
    const data = this._ledBuffer(colors);
    return this._locked(async () => {
      for (let i = 0; i < 6; i++)
        await this._write(this._report(CMD.FRAME_BASE + i,
          Array.from(data.slice(i * CHUNK, (i + 1) * CHUNK))));
    });
  }

  setSleep(option) { return this.send(CMD.SLEEP, [option]); }
  setResponse(gear) { return this.send(CMD.RESPONSE, [gear]); }
  setFnSwitch(on) { return this.send(CMD.FN_SWITCH, [on ? 1 : 0]); }

  async remap(layer, src, dst) {
    await this.send(CMD.REMAP, [layer + 1, src, dst]);
    await sleep(200);
  }

  async setMacro(layer, src, events, repeat = 1) {
    if (events.length > 60) throw new Error("at most 60 macro events");
    const body = [layer + 1, src, repeat & 0xff, events.length];
    for (const [code, release, delay] of events) body.push(code, encodeDelay(release, delay));
    const data = new Uint8Array(3 * CHUNK);
    data.set(body);
    await this._chunks(CMD.KEY_CHUNK0, data, 3, 20);
    await sleep(150);
  }

  async resetKeys() { await this.send(CMD.RESET_KEYS); await sleep(100); }
  async factoryReset() { await this.send(CMD.FACTORY_RESET); await sleep(100); }
}

// -- state (localStorage), same shape as ~/.config/openajazz/state.json -------
const STATE_KEY = "openajazz-state";
const OLD_STATE_KEY = "ak820ctl-state";  // name before 0.4

export function defaultState() {
  return {
    light: { mode: 7, brightness: 5, speed: 4, direction: 0, color: DATA.rainbow },
    lights_off: false, colors: {}, remaps: {}, macros: {},
    settings: { sleep: 1, response: 1, fn: false },
  };
}

export function loadState() {
  const st = defaultState();
  try {
    const saved = JSON.parse(localStorage.getItem(STATE_KEY) || localStorage.getItem(OLD_STATE_KEY) || "{}");
    for (const [k, v] of Object.entries(saved)) {
      if (st[k] && typeof st[k] === "object" && typeof v === "object") Object.assign(st[k], v);
      else if (k in st) st[k] = v;
    }
  } catch { /* corrupt or blocked storage: start fresh */ }
  return st;
}

export function saveState(st) {
  try { localStorage.setItem(STATE_KEY, JSON.stringify(st)); } catch { /* ignore */ }
}

// -- high-level operations (control.py) ------------------------------------
export const control = {
  async applyLight(kb, st, light) {
    await kb.setLight(light.mode, light.brightness, light.speed, light.direction, light.color);
    st.light = { ...light }; st.lights_off = false;
  },
  async uploadCustom(kb, st, colors, brightness) {
    brightness = brightness || st.light.brightness;
    await kb.setCustomColors(colors, brightness);
    st.colors = { ...colors };
    st.light = { ...st.light, mode: DATA.customMode, brightness };
    st.lights_off = false;
  },
  async lightsOff(kb, st) { await kb.lightsOff(); st.lights_off = true; },
  async lightsOn(kb, st) {
    const l = st.light;
    if (l.mode === DATA.customMode) await kb.setCustomColors(st.colors, l.brightness);
    else if (l.mode === 22 || l.mode === 23) await kb.setLight(7, l.brightness, l.speed, 0, DATA.rainbow);
    else await kb.setLight(l.mode, l.brightness, l.speed, l.direction, l.color);
    st.lights_off = false;
  },
  async remap(kb, st, layer, src, dst) {
    await kb.remap(layer, src, dst);
    st.remaps[`${layer}:${src}`] = dst;
    delete st.macros[`${layer}:${src}`];
  },
  async setMacro(kb, st, layer, src, raw, repeat) {
    await kb.setMacro(layer, src, parseMacroEvents(raw), repeat);
    st.macros[`${layer}:${src}`] = { events: raw, repeat };
    delete st.remaps[`${layer}:${src}`];
  },
  async replayKeys(kb, st) {
    await kb.resetKeys();
    for (const [key, dst] of Object.entries(st.remaps)) {
      const [layer, src] = key.split(":").map(Number);
      await kb.remap(layer, src, dst);
    }
    for (const [key, m] of Object.entries(st.macros)) {
      const [layer, src] = key.split(":").map(Number);
      await kb.setMacro(layer, src, parseMacroEvents(m.events), m.repeat);
    }
  },
  async restoreKey(kb, st, layer, src) {
    delete st.remaps[`${layer}:${src}`];
    delete st.macros[`${layer}:${src}`];
    await control.replayKeys(kb, st);
  },
  async resetKeys(kb, st) { await kb.resetKeys(); st.remaps = {}; st.macros = {}; },
  async applySettings(kb, st, sleepOpt, response, fn) {
    await kb.setSleep(sleepOpt); await kb.setResponse(response); await kb.setFnSwitch(fn);
    st.settings = { sleep: sleepOpt, response, fn };
  },
  async factoryReset(kb, st) {
    await kb.factoryReset();
    Object.assign(st, defaultState());
  },
};
