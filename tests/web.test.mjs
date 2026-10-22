// Checks the web app modules (node tests/web.test.mjs). No browser or keyboard needed.
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url)).replace(/\/$/, "");
globalThis.performance ??= { now: () => Date.now() };
const { DATA } = await import(root + "/web/data.js");
const fx = await import(root + "/web/effects.js");
const P = await import(root + "/web/protocol.js");
let fail = 0;
const eq = (a, b, msg) => { if (JSON.stringify(a) !== JSON.stringify(b)) { fail++; console.log("FAIL", msg, a, b); } };
// delay encoding must match protocol.py
eq([[0,5],[0,20],[1,310],[0,500],[0,2000],[1,5000]].map(([r,d]) => P.encodeDelay(r,d)), [0x01,0x02,0x9f,0x2a,0x34,0xe5], "encodeDelay");
eq(P.parseMacroEvents("+lctrl c -lctrl@500").map(e => [e[0], e[1], e[2]]), [[0xe0,false,10],[6,false,10],[6,true,10],[0xe0,true,500]], "macro parse");
eq(P.targetCode("volup"), 0xea, "media"); eq(P.keyCode("Esc"), 0x29, "esc"); eq(P.codeName(0xee), "playpause", "codeName");
for (const m of DATA.modes) {
  if ([22,23,24].includes(m.mode)) continue;
  const f = fx.previewFrame({ mode: m.mode, brightness: 5, speed: 3, direction: 1, color: 7 }, 1.3);
  if (Object.keys(f).length !== 82 || Object.values(f).some(c => c.some(v => !(v >= 0 && v <= 255)))) { fail++; console.log("bad preview", m.mode); }
}
for (const p of Object.keys(DATA.patterns)) { if (Object.keys(fx.pattern(p, [255,0,0], [0,0,255])).length !== 82) { fail++; console.log("bad pattern", p); } }
// simulated keyboard packets
const sent = [];
const kb = new P.Keyboard(null, { simulated: true, log: (l) => sent.push(l) });
await kb.setLight(8, 3, 2, 1, 5);
await kb.remap(1, 0x3a, 0xee);
await kb.setCustomColors({ 15: [255, 0, 0] }, 5);
const st = await kb.status();
eq(sent[0], "aa 55 cc 33 07 07 02 01 01 05", "light packet");
eq(sent[1], "aa 55 cc 33 04 02 3a ee", "remap packet");
eq(sent.slice(2, 4), ["aa 55 cc 33 07 17 04 03 00 07", "aa 55 cc 33 0b"], "custom begin");
eq([st.battery, st.powerName], [87, "on battery"], "status");
console.log(fail ? `${fail} failures` : "all web checks passed", "| packets:", sent.length);
if (fail) process.exit(1);

// Parity: the web previews must match openajazz/effects.py (same formulas, same truncation).
{
  const { execFileSync } = await import("node:child_process");
  const K = DATA.keys.find((k) => k.label === "K").led;
  const cases = [];
  for (const m of DATA.modes) {
    if ([22, 23, 24].includes(m.mode)) continue;
    for (const t of [0.37, 2.9]) cases.push([m.mode, 4, 3, m.mode % 2, 7, t]);
  }
  cases.push([7, 5, 3, 0, 2, 1.0]);  // fixed palette colour
  const py = JSON.parse(execFileSync("python3", ["-c", `
import json, sys
sys.path.insert(0, ${JSON.stringify(root)})
from openajazz import effects
cases = json.loads(sys.argv[1])
print(json.dumps([{str(k): list(v) for k, v in effects.frame(*c[:5], t=c[5], presses=[(${K}, c[5] - 0.2)]).items()} for c in cases]))
`, JSON.stringify(cases)]).toString());
  let diffs = 0;
  cases.forEach(([mode, b, s, d, c, t], i) => {
    const js = fx.previewFrame({ mode, brightness: b, speed: s, direction: d, color: c }, t, {}, [[K, t - 0.2]]);
    for (const [led, rgb] of Object.entries(py[i])) {
      if (rgb.some((v, j) => Math.abs(v - js[led][j]) > 1)) { diffs++; if (diffs < 4) console.log("parity", mode, t, led, rgb, js[led]); }
    }
  });
  if (diffs) { fail++; console.log(`FAIL preview parity: ${diffs} LEDs differ`); }
  else console.log(`preview parity ok (${cases.length} cases)`);
}
if (fail) process.exit(1);
