"use strict";

const BASELINE = "pillow-13.0.0";
const ISA = { scalar: "scalar", sse4: "SSE4", avx2: "AVX2", avxvnni: "AVX-VNNI", neon: "NEON" };
const ISA_ORDER = ["scalar", "sse4", "avx2", "avxvnni", "neon"];
const FAMILIES = [
  { id: "upstream", label: "Pillow 13.0", color: "--upstream" },
  { id: "release", label: "Pillow-SIMD 12.1 release", color: "--release" },
  { id: "branch", label: "Pillow-AllSIMD 13", color: "--branch" },
  { id: "fast", label: "Pillow-AllSIMD 13 fast mode", color: "--fast" },
  { id: "opencv", label: "OpenCV", color: "--other" },
  { id: "vips", label: "libvips", color: "--other" },
  { id: "wand", label: "ImageMagick", color: "--other" },
];
const UNITS = { mpx: "Mpx/s", shapes: "shapes/s", lines: "lines/s" };

const state = { machines: [], data: null, machine: null, hidden: new Set(), views: {} };

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k === "style") e.setAttribute("style", v);
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const kid of kids) if (kid != null) e.append(kid);
  return e;
}

/* Variant name -> label, family and sort key. */
function describe(name, v) {
  let m;
  if ((m = name.match(/^branch-(\w+)-fast$/))) {
    return { label: `Pillow-AllSIMD 13 ${ISA[m[1]] || m[1]} fast`, fam: "fast", order: 30 + ISA_ORDER.indexOf(m[1]) };
  }
  if (name.startsWith("branch-")) {
    const isa = name.slice(7);
    return { label: `Pillow-AllSIMD 13 ${ISA[isa] || isa}`, fam: "branch", order: 20 + ISA_ORDER.indexOf(isa) };
  }
  if ((m = name.match(/^pillow-simd-(\d+\.\d+\.\d+)(?:\.post\d+)?-(\w+)$/))) {
    return { label: `Pillow-SIMD ${m[1]} ${ISA[m[2]] || m[2]}`, fam: "release", order: 10 + ISA_ORDER.indexOf(m[2]) };
  }
  if (name.startsWith("pillow-")) return { label: `Pillow ${v.version}`, fam: "upstream", order: 0 };
  const libs = { opencv: ["OpenCV", 40], vips: ["libvips", 41], wand: ["ImageMagick", 42] };
  const [lib, order] = libs[name] || [name, 50];
  return { label: `${lib} ${v.version}`, fam: name, order };
}

function famColor(fam) {
  const f = FAMILIES.find((x) => x.id === fam);
  return `var(${f ? f.color : "--other"})`;
}

function fmt(v) {
  if (v >= 1000) return Math.round(v).toLocaleString("en-US");
  if (v >= 100) return v.toFixed(0);
  if (v >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

function rate(meta, r) {
  const [w, h] = state.data.size;
  const work = meta.work === "mpx" ? (w * h) / 1e6 : meta.n;
  return work / r.best;
}

function variants() {
  return Object.entries(state.data.variants)
    .map(([name, v]) => ({ name, v, ...describe(name, v) }))
    .sort((a, b) => a.order - b.order);
}

/* ------------------------------------------------------------ tooltip */

const tip = document.getElementById("tip");
function showTip(ev, parts) {
  tip.replaceChildren(...parts);
  tip.hidden = false;
  const r = (ev.currentTarget || ev.target).getBoundingClientRect();
  const x = Math.min(window.innerWidth - tip.offsetWidth - 8, Math.max(8, r.left));
  let y = r.bottom + 6;
  if (y + tip.offsetHeight > window.innerHeight - 8) y = r.top - tip.offsetHeight - 6;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
function hideTip() { tip.hidden = true; }

/* ------------------------------------------------------------ charts */

function barRows(rows, unit) {
  const max = Math.max(...rows.filter((r) => r.value != null).map((r) => r.value), 1e-9);
  const bars = el("div", { class: "bars" });
  for (const r of rows) {
    const row = el("div", { class: "row" + (r.value == null ? " missing" : "") });
    const name = el("div", { class: "name", title: r.label, text: r.label });
    if (r.noteMark) name.append(el("sup", { text: r.noteMark }));
    const track = el("div", { class: "track" });
    const val = el("div", { class: "val" });
    if (r.value != null) {
      track.tabIndex = 0;
      track.setAttribute("aria-label", `${r.label}: ${fmt(r.value)} ${unit}`);
      track.append(el("div", { class: "bar", style: `width:${(100 * r.value) / max}%;background:${r.color}` }));
      const x = r.ratio;
      const cls = x == null ? "x" : x > 1.05 ? "x up" : x < 0.95 ? "x down" : "x";
      val.append(el("span", { class: cls, text: x == null ? "" : `${x >= 10 ? x.toFixed(0) : x.toFixed(2)}×` }), " ", fmt(r.value));
      const parts = () => {
        const out = [
          el("div", { class: "v", text: `${fmt(r.value)} ${unit}` }),
          el("div", { class: "s" }, el("span", { class: "k", style: `background:${r.color}` }), r.label),
        ];
        if (r.detail) out.push(el("div", { class: "s", text: r.detail }));
        if (r.note) out.push(el("div", { class: "n", text: r.note }));
        return out;
      };
      for (const t of ["pointerenter", "focus"]) track.addEventListener(t, (ev) => showTip(ev, parts()));
      for (const t of ["pointerleave", "blur"]) track.addEventListener(t, hideTip);
    } else {
      val.textContent = "n/a";
    }
    row.append(name, track, val);
    bars.append(row);
  }
  return bars;
}

/* Notes a library has on every case of a suite: shown once, under the
   suite's heading, instead of under each chart. */
function sharedNotes(suiteCases) {
  const shared = new Map();
  for (const d of variants()) {
    if (state.hidden.has(d.fam)) continue;
    const notes = suiteCases.filter(([cid]) => d.v.results[cid]).map(([cid]) => d.v.notes?.[cid]);
    if (notes.length > 1 && notes[0] && notes.every((n) => n === notes[0])) shared.set(d.name, notes[0]);
  }
  return shared;
}

function caseCard(cid, meta, shared) {
  const unit = UNITS[meta.work];
  const base = state.data.variants[BASELINE]?.results[cid];
  const rows = [];
  const notes = [];
  for (const d of variants()) {
    if (state.hidden.has(d.fam)) continue;
    const r = d.v.results[cid];
    const note = d.v.notes?.[cid];
    let noteMark = null;
    if (note && !shared.has(d.name)) {
      noteMark = String(notes.length + 1);
      notes.push(`${noteMark} ${d.label.split(" ")[0]}: ${note}`);
    }
    if (!r) {
      if (["upstream", "branch", "fast", "release"].includes(d.fam)) rows.push({ label: d.label, value: null });
      continue;
    }
    rows.push({
      label: d.label,
      value: rate(meta, r),
      ratio: base ? base.best / r.best : null,
      color: famColor(d.fam),
      note,
      noteMark,
      detail: `best ${(r.best * 1000).toFixed(2)} ms, median ${(r.median * 1000).toFixed(2)} ms, ${r.runs} runs`,
    });
  }
  const card = el("div", { class: "card" }, el("h3", {}, meta.title, " ", el("span", { class: "unit", text: unit })));
  card.append(barRows(rows, unit));
  if (notes.length) card.append(el("ul", { class: "notes" }, ...notes.map((n) => el("li", { text: n }))));
  return card;
}

function suiteTable(suiteCases) {
  const vs = variants().filter((d) => !state.hidden.has(d.fam));
  const head = el("tr", {}, el("th", { text: "Case" }), ...vs.map((d) => el("th", { text: d.label })));
  const body = suiteCases.map(([cid, meta]) =>
    el(
      "tr",
      {},
      el("td", { text: `${meta.title} (${UNITS[meta.work]})` }),
      ...vs.map((d) => {
        const r = d.v.results[cid];
        return r ? el("td", { text: fmt(rate(meta, r)) }) : el("td", { class: "na", text: "–" });
      }),
    ),
  );
  return el("div", { class: "tablewrap" }, el("table", { class: "data" }, el("thead", {}, head), el("tbody", {}, ...body)));
}

/* Geometric mean of the speed relative to the baseline, over the cases
   that both have. */
function geomean(d, cids) {
  const base = state.data.variants[BASELINE];
  let s = 0;
  let n = 0;
  for (const cid of cids) {
    const a = base?.results[cid];
    const b = d.v.results[cid];
    if (a && b) {
      s += Math.log(a.best / b.best);
      n += 1;
    }
  }
  return n ? { x: Math.exp(s / n), n } : null;
}

function renderSummary() {
  const sec = document.getElementById("summary");
  const cids = Object.keys(state.data.cases);
  const rows = [];
  for (const d of variants()) {
    if (state.hidden.has(d.fam)) continue;
    if (d.name === BASELINE) {
      rows.push({ label: d.label, value: 1, ratio: null, color: famColor(d.fam), detail: "the baseline" });
      continue;
    }
    const g = geomean(d, cids);
    if (!g) continue;
    rows.push({
      label: d.label,
      value: g.x,
      ratio: null,
      color: famColor(d.fam),
      detail: `over the ${g.n} cases it shares with Pillow 13.0.0`,
    });
  }
  const card = el(
    "div",
    { class: "card" },
    el("h3", {}, "Speed relative to Pillow 13.0.0 ", el("span", { class: "unit", text: "geometric mean, ×" })),
  );
  const bars = barRows(rows, "×");
  for (const v of bars.querySelectorAll(".val")) v.firstChild?.remove();
  card.append(bars);
  card.append(
    el("ul", { class: "notes" }, el("li", { text: "Each library is averaged over the cases it implements, so the libraries are not averaged over the same set." })),
  );

  const suiteIds = state.data.suites.map((s) => s.id);
  const vs = variants().filter((d) => !state.hidden.has(d.fam) && d.name !== BASELINE);
  const head = el("tr", {}, el("th", { text: "Suite" }), ...vs.map((d) => el("th", { text: d.label })));
  const body = suiteIds.map((sid) => {
    const ids = cids.filter((c) => state.data.cases[c].suite === sid);
    const title = state.data.suites.find((s) => s.id === sid).title;
    return el(
      "tr",
      {},
      el("td", {}, el("a", { href: `#suite-${sid}`, text: title })),
      ...vs.map((d) => {
        const g = geomean(d, ids);
        return g ? el("td", { text: `${g.x.toFixed(2)}×` }) : el("td", { class: "na", text: "–" });
      }),
    );
  });
  sec.replaceChildren(
    el("header", {}, el("h2", { text: "Summary" }), el("span", { class: "about", text: "Speed relative to Pillow 13.0.0: above 1× is faster." })),
    el("div", { class: "grid", style: "grid-template-columns:1fr" }, card),
    el("div", { class: "tablewrap" }, el("table", { class: "data" }, el("thead", {}, head), el("tbody", {}, ...body))),
  );
}

function renderSuites() {
  const main = document.getElementById("suites");
  main.replaceChildren();
  const jump = document.getElementById("jump");
  jump.replaceChildren(el("option", { value: "summary", text: "Summary" }));
  for (const s of state.data.suites) {
    const suiteCases = Object.entries(state.data.cases).filter(([, m]) => m.suite === s.id);
    if (!suiteCases.length) continue;
    jump.append(el("option", { value: `suite-${s.id}`, text: s.title }));
    const view = state.views[s.id] || "chart";
    const toggle = el(
      "div",
      { class: "seg view", role: "group", "aria-label": `${s.title} view` },
      ...["chart", "table"].map((v) =>
        el("button", {
          type: "button",
          "aria-pressed": String(view === v),
          text: v === "chart" ? "Charts" : "Table",
          onclick: () => {
            state.views[s.id] = v;
            renderSuites();
            document.getElementById(`suite-${s.id}`).scrollIntoView();
          },
        }),
      ),
    );
    const sec = el(
      "section",
      { class: "suite", id: `suite-${s.id}` },
      el("header", {}, el("h2", { text: s.title }), el("span", { class: "about", text: s.about }), toggle),
    );
    const shared = sharedNotes(suiteCases);
    if (shared.size) {
      const label = (name) => variants().find((d) => d.name === name).label.split(" ")[0];
      sec.append(el("ul", { class: "notes suite-notes" }, ...[...shared].map(([n, t]) => el("li", { text: `${label(n)}: ${t}` }))));
    }
    if (view === "table") sec.append(suiteTable(suiteCases));
    else sec.append(el("div", { class: "grid" }, ...suiteCases.map(([cid, meta]) => caseCard(cid, meta, shared))));
    main.append(sec);
  }
}

function renderMeta() {
  const d = state.data;
  const m = d.machine;
  const meta = document.getElementById("meta");
  meta.replaceChildren(
    el("strong", { text: d.title }),
    ` · ${m.machine}, ${m.Vendor_ID || m["Vendor ID"] || ""} · Python ${m.python}, GCC ${m.gcc} · `,
    `branch ${m.branch} @ `,
    el("a", { href: `https://github.com/desmoteo/pillow-allsimd/commit/${m.commit}`, text: m.commit }),
    ` · ${d.size[0]}×${d.size[1]} · measured ${d.date}`,
  );
  const legend = document.getElementById("legend");
  const fams = new Set(variants().map((x) => x.fam));
  legend.replaceChildren(
    ...FAMILIES.filter((f) => fams.has(f.id) && !["vips", "wand"].includes(f.id)).map((f) =>
      el("span", {}, el("i", { style: `background:var(${f.color})` }), f.id === "opencv" ? "Other libraries" : f.label),
    ),
  );
  const versions = document.getElementById("versions");
  versions.replaceChildren(
    el("thead", {}, el("tr", {}, el("th", { text: "Build" }), el("th", { text: "Version" }), el("th", { text: "Cases" }))),
    el(
      "tbody",
      {},
      ...variants().map((x) =>
        el("tr", {}, el("td", { text: x.label }), el("td", { text: x.v.version }), el("td", { text: String(Object.keys(x.v.results).length) })),
      ),
    ),
  );
}

function renderControls() {
  const box = document.getElementById("machines");
  box.replaceChildren(
    ...state.machines.map((m) =>
      el("button", {
        type: "button",
        "aria-pressed": String(m.id === state.machine),
        text: m.label,
        onclick: () => load(m.id),
      }),
    ),
  );
  const fams = new Set(variants().map((x) => x.fam));
  const chips = document.getElementById("families");
  chips.replaceChildren(
    ...FAMILIES.filter((f) => fams.has(f.id)).map((f) => {
      const input = el("input", { type: "checkbox" });
      input.checked = !state.hidden.has(f.id);
      input.addEventListener("change", () => {
        if (input.checked) state.hidden.delete(f.id);
        else state.hidden.add(f.id);
        render();
      });
      return el("label", { class: "chip" }, input, el("span", { class: "key", style: `background:var(${f.color})` }), f.label);
    }),
  );
}

function render() {
  renderControls();
  renderMeta();
  renderSummary();
  renderSuites();
}

async function load(id) {
  const m = state.machines.find((x) => x.id === id) || state.machines[0];
  state.machine = m.id;
  history.replaceState(null, "", `#${m.id}`);
  const res = await fetch(`data/${m.file}`);
  state.data = await res.json();
  render();
}

document.getElementById("jump").addEventListener("change", (ev) => {
  document.getElementById(ev.target.value)?.scrollIntoView();
});

(async () => {
  const res = await fetch("data/index.json");
  state.machines = (await res.json()).machines;
  await load(location.hash.slice(1));
})();
