"use strict";
/* karte – grafičko sučelje (vanilla JS, bez vanjskih biblioteka) */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf0 = new Intl.NumberFormat("hr-HR", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("hr-HR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const isNum = (v) => typeof v === "number" && isFinite(v);
const eur = (v, d = 0) => (!isNum(v) ? "—" : (d ? nf2 : nf0).format(Math.abs(v) < (d ? 0.005 : 0.5) ? 0 : v) + " €");
const pct = (v) => (!isNum(v) ? "—" : (v >= 0 ? "+" : "−") + nf0.format(Math.abs(v * 100)) + " %");
const mult = (v) => (!isNum(v) ? "—" : "×" + v.toFixed(2).replace(".", ","));
const score = (v) => (!isNum(v) ? "—" : nf0.format(v * 100));
const pad = (n) => String(n).padStart(2, "0");
function parseIso(iso) {
  if (!iso) return null;
  const d = new Date(String(iso).replace(" ", "T"));
  return isNaN(d) ? null : d;
}
function dateFmt(iso) {
  const d = parseIso(iso);
  return d ? `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}.` : "—";
}
function dtFmt(iso) {
  const d = parseIso(iso);
  if (!d) return "—";
  return d.getHours() || d.getMinutes() ? `${dateFmt(iso)} ${pad(d.getHours())}:${pad(d.getMinutes())}` : dateFmt(iso);
}
const todayIso = () => new Date().toISOString().slice(0, 10);

const VERDICT_CLASS = {
  KUPI: "v-buy", RAZMOTRI: "v-maybe", "PROVJERI CIJENU": "v-check", RASPRODANO: "v-sold", "PRESKOČI": "v-skip",
  "ZAKONSKI OGRANIČENO": "v-legal", "UVJETI ZABRANJUJU": "v-legal", "NEMA CIJENE": "v-skip", OTKAZANO: "v-skip",
};
const plural = (n, one, other) => (n % 10 === 1 && n % 100 !== 11 ? one : other);
const pill = (v) => `<span class="pill ${VERDICT_CLASS[v] || "v-skip"}">${esc(v)}</span>`;
const REGION_LABELS = {
  otvoreno: "Otvorena tržišta (preporučeno)", svijet: "Cijeli svijet", europa: "Europa", zapadna_europa: "Zapadna Europa",
  srednja_europa: "Srednja Europa", dach: "DACH (DE, AT, CH)", benelux: "Benelux", nordijske: "Nordijske zemlje",
  balkan: "Balkan", sjeverna_amerika: "Sjeverna Amerika", latam: "Latinska Amerika", oceanija: "Australija i NZ", azija: "Azija",
};

const state = { meta: null, scan: null, filter: "SVE", search: "", sort: { k: null, dir: 1 }, journal: null, guides: null, loaded: {} };

/* ------------------------------------------------------------------ API */
const api = {
  async req(url, opts = {}) {
    const r = await fetch(url, opts);
    const ct = r.headers.get("content-type") || "";
    const data = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok) throw new Error((data && data.error) || r.statusText);
    return data;
  },
  get: (url) => api.req(url),
  post: (url, body) => api.req(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  del: (url) => api.req(url, { method: "DELETE" }),
  async download(url, body, filename) {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json()).error || r.statusText);
    saveBlob(await r.blob(), filename);
  },
};
function saveBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 3500);
}
async function busy(btn, fn) {
  const label = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Radim…`;
  try { return await fn(); }
  catch (e) { toast("Greška: " + e.message); }
  finally { btn.disabled = false; btn.innerHTML = label; }
}

/* ------------------------------------------------------------------ tema i kartice */
function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("karte-theme"); } catch (e) { /* bez storagea */ }
  if (saved) document.documentElement.dataset.theme = saved;
  $("#themeBtn").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("karte-theme", next); } catch (e) { /* */ }
    rerenderCharts();
  });
}
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${name}`));
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "markets" && !state.loaded.markets) loadMarkets();
  if (name === "journal" && !state.loaded.journal) loadJournal();
  if (name === "guides" && !state.loaded.guides) loadGuides();
  rerenderCharts();
}

/* ------------------------------------------------------------------ obrasci */
function countryOptions(selected) {
  return state.meta.countries.map((c) => `<option value="${esc(c.code)}"${c.code === selected ? " selected" : ""}>${esc(c.name)} (${esc(c.code)})</option>`).join("");
}
const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "HUF", "CZK", "PLN", "SEK", "DKK", "NOK", "RSD", "BAM", "CAD", "AUD", "MXN"];

function eventFields() {
  return [
    { k: "segment", l: "Vrsta", t: "select", opts: [["music", "Koncert"], ["sport", "Sport"]] },
    { k: "artist", l: "Izvođač / domaći klub", req: true },
    { k: "name", l: "Naziv (npr. 'Dinamo – Hajduk')" },
    { k: "sport", l: "Sport (ako je sport)", t: "select", opts: Object.entries(state.meta.sports) },
    { k: "league", l: "Natjecanje / liga", ph: "npr. UEFA Champions League, NFL" },
    { k: "venue", l: "Dvorana", ph: "npr. Arena Zagreb" },
    { k: "city", l: "Grad" },
    { k: "country", l: "Država", t: "country", def: "HR" },
    { k: "region", l: "Savezna država / pokrajina", ph: "samo SAD/Kanada/AU, npr. NY" },
    { k: "date", l: "Datum koncerta", t: "date" },
    { k: "face", l: "Nominalna cijena (najjeftinija)", t: "number", step: "0.01" },
    { k: "face_max", l: "Nominalna (najskuplja, opcionalno)", t: "number", step: "0.01" },
    { k: "currency", l: "Valuta", t: "select", opts: CURRENCIES.map((c) => [c, c]) },
    { k: "resale_lowest", l: "Najniža cijena na viagogu", t: "number", step: "0.01", ph: "ukupna cijena koju vidi kupac" },
    { k: "listing_count", l: "Broj oglasa na viagogu", t: "number" },
    { k: "listeners", l: "Last.fm slušatelji", t: "number", lastfm: true },
    { k: "fans", l: "Deezer fanovi (bez ključa)", t: "number", deezer: true },
    { k: "capacity", l: "Kapacitet (prazno = automatski)", t: "number" },
    { k: "ticket_limit", l: "Limit ulaznica po kupcu", t: "number" },
    { k: "vendor", l: "Gdje se kupuje", t: "select", opts: Object.entries(state.meta.vendors) },
    { k: "personalized", l: "Personalizirane ulaznice?", t: "select", opts: [["", "Ne znam"], ["ne", "Ne"], ["da", "Da (ime na ulaznici)"]] },
    { k: "onsale", l: "Početak prodaje (ako još nije)", t: "datetime-local" },
    { k: "budget", l: "Budžet (€)", t: "number", def: state.meta.settings.budget },
  ];
}
function buildFields(container, fields) {
  container.innerHTML = fields.map((f) => {
    const id = `${container.id}-${f.k}`;
    let input;
    if (f.t === "country") input = `<select id="${id}" name="${f.k}">${countryOptions(f.def || "HR")}</select>`;
    else if (f.t === "select") input = `<select id="${id}" name="${f.k}">${f.opts.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join("")}</select>`;
    else if (f.t === "datalist") input = `<input id="${id}" name="${f.k}" list="${id}-dl" autocomplete="off"><datalist id="${id}-dl">${f.opts.map((o) => `<option value="${esc(o)}">`).join("")}</datalist>`;
    else input = `<input id="${id}" name="${f.k}" type="${f.t || "text"}"${f.step ? ` step="${f.step}"` : ""}${f.ph ? ` placeholder="${esc(f.ph)}"` : ""}${f.req ? " required" : ""}${f.def != null ? ` value="${esc(f.def)}"` : ""} autocomplete="off">`;
    if (f.lastfm) {
      const on = state.meta.settings.lastfm;
      input = `<div class="row" style="margin:0;flex-wrap:nowrap">${input}<button type="button" class="ghost small" data-lastfm="${container.id}"${on ? "" : ' disabled title="Dodaj LASTFM_API_KEY u .env"'}>Dohvati</button></div>`;
    }
    if (f.deezer) {
      input = `<div class="row" style="margin:0;flex-wrap:nowrap">${input}<button type="button" class="ghost small" data-deezer="${container.id}" title="Deezer fanovi + trend na Wikipediji (bez ključa)">Dohvati</button></div>`;
    }
    return `<label for="${id}">${esc(f.l)}${input}</label>`;
  }).join("");
  $$("[data-lastfm]", container).forEach((b) => b.addEventListener("click", async () => {
    const artist = $(`[name="artist"]`, container).value.trim();
    if (!artist) return toast("Upiši izvođača.");
    await busy(b, async () => {
      const r = await api.get(`/api/listeners?artist=${encodeURIComponent(artist)}`);
      if (r.listeners) $(`[name="listeners"]`, container).value = r.listeners;
      else toast(r.error || "Izvođač nije pronađen na Last.fm-u.");
    });
  }));
  $$("[data-deezer]", container).forEach((b) => b.addEventListener("click", async () => {
    const artist = $(`[name="artist"]`, container).value.trim();
    if (!artist) return toast("Upiši izvođača.");
    await busy(b, async () => {
      const r = await api.get(`/api/popularity?artist=${encodeURIComponent(artist)}`);
      if (r.fans) $(`[name="fans"]`, container).value = r.fans;
      const trend = isNum(r.trend) ? ` · Wikipedia trend ×${r.trend.toFixed(2)}${r.trend >= 1.15 ? " (raste interes)" : ""}` : "";
      toast(r.fans ? `Deezer: ${nf0.format(r.fans)} fanova${trend}` : (r.error || "Izvođač nije pronađen na Deezeru (provjeri točno ime)."));
    });
  }));
}
function buildTags(container) {
  container.innerHTML = Object.entries(state.meta.tags)
    .map(([k, l]) => `<label class="check"><input type="checkbox" value="${esc(k)}"> ${esc(l)}</label>`).join("");
}
function readFields(container, tagsContainer) {
  const out = {};
  $$("input[name], select[name]", container).forEach((el) => { if (el.value !== "") out[el.name] = el.value; });
  if (tagsContainer) out.tags = $$("input:checked", tagsContainer).map((c) => c.value);
  return out;
}
function fillFields(container, data, tagsContainer) {
  $$("input[name], select[name]", container).forEach((el) => {
    if (data[el.name] !== undefined && data[el.name] !== null) el.value = data[el.name];
  });
  if (tagsContainer) $$("input", tagsContainer).forEach((c) => (c.checked = (data.tags || []).includes(c.value)));
}

/* ------------------------------------------------------------------ graf (vodoravni stupci) */
const charts = {};
function barChart(id, items, opts = {}) {
  charts[id] = { items, opts };
  drawBarChart(id);
}
function rerenderCharts() { Object.keys(charts).forEach(drawBarChart); }
function niceTicks(min, max, count = 4) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count + 0.5) || step0;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) { const t = +v.toFixed(10); ticks.push(t === 0 ? 0 : t); }
  return ticks;
}
function drawBarChart(id) {
  const el = document.getElementById(id);
  const cfg = charts[id];
  if (!el || !cfg || !el.offsetParent) return;
  const { items, opts } = cfg;
  if (!items.length) { el.innerHTML = '<p class="muted">Nema podataka za graf.</p>'; return; }
  const W = Math.max(280, el.clientWidth);
  const narrow = W < 560;
  const labelW = narrow ? 118 : 230, valueW = 70, rowH = 28, barH = 16, topPad = 6, axisH = 22;
  const plotW = Math.max(60, W - labelW - valueW);
  const vals = items.map((d) => d.value);
  const min = Math.min(0, ...vals), max = Math.max(0, ...vals, opts.ref || 0);
  const x = (v) => labelW + ((v - min) / (max - min || 1)) * plotW;
  const zero = x(0);
  const H = topPad + items.length * rowH + axisH;
  const maxChars = Math.floor(labelW / 7.2);
  const cut = (s) => (s.length > maxChars ? s.slice(0, maxChars - 1) + "…" : s);
  const ticks = niceTicks(min, max);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.title || "Graf")}">`;
  ticks.forEach((t) => {
    svg += `<line class="gridline" x1="${x(t)}" x2="${x(t)}" y1="${topPad}" y2="${H - axisH}"/>`;
    svg += `<text class="val" x="${x(t)}" y="${H - 6}" text-anchor="middle">${esc(opts.tick ? opts.tick(t) : t)}</text>`;
  });
  if (opts.ref != null) {
    svg += `<line class="axis" x1="${x(opts.ref)}" x2="${x(opts.ref)}" y1="${topPad}" y2="${H - axisH}" stroke-dasharray="4 3"/>`;
  }
  items.forEach((d, i) => {
    const y = topPad + i * rowH + (rowH - barH) / 2;
    const xv = x(d.value), r = Math.min(4, Math.abs(xv - zero));
    const neg = d.value < 0;
    const path = neg
      ? `M${zero},${y} H${xv + r} Q${xv},${y} ${xv},${y + r} V${y + barH - r} Q${xv},${y + barH} ${xv + r},${y + barH} H${zero} Z`
      : `M${zero},${y} H${xv - r} Q${xv},${y} ${xv},${y + r} V${y + barH - r} Q${xv},${y + barH} ${xv - r},${y + barH} H${zero} Z`;
    svg += `<g class="row" data-i="${i}" tabindex="0" role="button" aria-label="${esc(d.label)}: ${esc(opts.fmt(d.value))}">`;
    svg += `<rect class="hit" x="0" y="${topPad + i * rowH}" width="${W}" height="${rowH}"/>`;
    svg += `<text class="lbl" x="${labelW - 8}" y="${y + barH - 3}" text-anchor="end">${esc(cut(d.label))}</text>`;
    svg += `<path class="bar${neg && opts.diverging ? " neg" : ""}" d="${path}"/>`;
    svg += neg
      ? `<text class="val" x="${zero + 6}" y="${y + barH - 3}">${esc(opts.fmt(d.value))}</text>`
      : `<text class="val" x="${xv + 6}" y="${y + barH - 3}">${esc(opts.fmt(d.value))}</text>`;
    svg += `</g>`;
  });
  svg += `<line class="axis" x1="${zero}" x2="${zero}" y1="${topPad}" y2="${H - axisH}"/></svg>`;
  let legend = "";
  if (opts.diverging) legend = `<div class="legend"><span><i style="background:var(--series-1)"></i>Dobit</span><span><i style="background:var(--neg)"></i>Gubitak</span></div>`;
  if (opts.ref != null && opts.refLabel) legend += `<div class="legend"><span>┆ ${esc(opts.refLabel)}</span></div>`;
  el.classList.add("chart");
  el.innerHTML = svg + legend;
  const tip = $("#tooltip");
  $$("g.row", el).forEach((g) => {
    const d = items[+g.dataset.i];
    const show = (ev) => {
      tip.innerHTML = d.tooltip || `${esc(d.label)}: ${esc(opts.fmt(d.value))}`;
      tip.hidden = false;
      const r = g.getBoundingClientRect();
      const px = ev && ev.clientX ? ev.clientX : r.left + r.width / 2;
      const py = ev && ev.clientY ? ev.clientY : r.top;
      tip.style.left = Math.min(window.innerWidth - tip.offsetWidth - 8, px + 12) + "px";
      tip.style.top = Math.max(8, py - tip.offsetHeight - 10) + "px";
    };
    g.addEventListener("mousemove", show);
    g.addEventListener("focus", () => show());
    g.addEventListener("mouseleave", () => (tip.hidden = true));
    g.addEventListener("blur", () => (tip.hidden = true));
    if (d.onClick) {
      g.style.cursor = "pointer";
      g.addEventListener("click", d.onClick);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter") d.onClick(); });
    }
  });
}
let resizeT;
window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(rerenderCharts, 150); });

/* ------------------------------------------------------------------ RADAR */
function initRadar() {
  const m = state.meta;
  const def = (m.settings.countries || "otvoreno").toLowerCase();
  const presets = Object.keys(m.regions);
  $("#presetSel").innerHTML = presets.map((r) => `<option value="${esc(r)}"${r === def ? " selected" : ""}>${esc(REGION_LABELS[r] || r)}</option>`).join("")
    + `<option value=""${presets.includes(def) ? "" : " selected"}>Vlastiti popis →</option>`;
  if (!presets.includes(def)) $("#customCountries").value = m.settings.countries;
  $("#categorySel").innerHTML = Object.entries(m.categories).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("");
  $("#sellerSel").innerHTML = countryOptions(m.settings.seller_country);
  $("#scanForm [name=budget]").value = m.settings.budget;
  const live = (m.settings.live_sources || []).length > 0;
  $("#sourceSel").value = live ? "live" : "snapshot";
  const hint = () => {
    const src = $("#sourceSel").value, snap = m.snapshot;
    $("#scanHint").textContent = src === "snapshot"
      ? (snap ? `Snimka od ${snap.date_hr}: ukupno ${snap.curated} provjerenih + ${snap.tour_events} ${plural(snap.tour_events, "datum", "datuma")} turneja u Europi. Osvježi: karte snimka --osvjezi` : "Snimka nije dostupna.")
      : src === "demo" ? "Izmišljeni podaci – samo za isprobavanje sučelja."
      : live ? `Izvori: ${m.settings.live_sources.join(", ")}` : "Nema ključa ni za jedan živi izvor – vidi docs/IZVORI_PODATAKA.md (npr. besplatni SERPAPI_KEY).";
  };
  $("#sourceSel").addEventListener("change", hint);
  hint();
  $("#scanForm").addEventListener("submit", (e) => { e.preventDefault(); runScan(); });
  $$("[data-export]").forEach((b) => b.addEventListener("click", () => busy(b, async () => {
    const body = await scanBody();
    body.format = b.dataset.export;
    await api.download("/api/report", body, `izvjestaj.${body.format}`);
  })));
  $("#searchBox").addEventListener("input", (e) => { state.search = e.target.value.toLowerCase(); renderResults(); });
}
async function scanBody() {
  const f = $("#scanForm");
  const fd = new FormData(f);
  const body = {
    countries: (fd.get("custom") || "").trim() || fd.get("preset") || "otvoreno",
    days: fd.get("days"), onsale_days: fd.get("onsale_days"), budget: fd.get("budget"),
    category: fd.get("category"), seller_country: fd.get("seller_country"), segment: fd.get("segment"),
    source: fd.get("source") || "snapshot", strict: !!fd.get("strict"), show_all: !!fd.get("show_all"),
  };
  const file = fd.get("csv");
  if (file && file.size) { body.csv_text = await file.text(); body.csv_name = file.name; }
  return body;
}
async function runScan() {
  await busy($("#scanBtn"), async () => {
    state.scan = await api.post("/api/scan", await scanBody());
    state.filter = "SVE";
    renderScan();
  });
}
function renderScan() {
  const s = state.scan;
  const ops = s.opportunities;
  let html = "";
  if (s.is_demo) html += `<div class="notice demo">DEMO PODACI – izvođači, cijene i brojke su izmišljeni (služe samo za prikaz rada aplikacije).</div>`;
  if (s.is_snapshot && s.snapshot) {
    const sn = s.snapshot;
    html += `<div class="notice info"><b>Stvarni podaci – snimka od ${esc(sn.date_hr)}</b> (${sn.curated} provjerenih ${plural(sn.curated, "događaj", "događaja")} + ${sn.tour_events} ${plural(sn.tour_events, "datum", "datuma")} turneja s Wikipedije). `
      + `Nominalne cijene najčešće nisu javne, pa za takve događaje piše <b>PROVJERI CIJENU</b> i do koje se cijene isplati kupiti (izračunato iz cijena na preprodaji). `
      + `Cijene s preprodaje su „od” cijene s agregatora uz datum – provjeri aktualne prije kupnje.${sn.age_days > 30 ? ` <b>Snimka je stara ${sn.age_days} dana – osvježi: karte snimka --osvjezi.</b>` : ""}</div>`;
  }
  html += `<div class="notice small"><b>Države:</b> ${esc(s.countries.join(", "))} · <b>Izvori:</b> ${esc(s.sources.join("; ") || "—")}</div>`;
  if (s.warnings.length) html += `<div class="notice warn small"><b>Napomene</b><ul>${s.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>`;
  $("#scanStatus").innerHTML = html;

  const buys = ops.filter((o) => o.verdict === "KUPI" || o.verdict === "RAZMOTRI");
  const invest = buys.reduce((a, o) => a + (o.buy_cost || 0) * o.suggested_qty, 0);
  const ev = buys.reduce((a, o) => a + (o.total_expected_value || 0), 0);
  const checks = ops.filter((o) => o.verdict === "PROVJERI CIJENU").length;
  $("#scanKpis").innerHTML = [
    ["Događaja", nf0.format(ops.length)],
    ["KUPI / RAZMOTRI", `${ops.filter((o) => o.verdict === "KUPI").length} / ${ops.filter((o) => o.verdict === "RAZMOTRI").length}`],
    ...(checks ? [["Provjeri cijenu", nf0.format(checks)]] : []),
    ["Preporučeno ulaganje", eur(invest)],
    ["Očekivana dobit (uz rizik)", eur(ev)],
  ].map(([l, v]) => `<div class="kpi"><span>${l}</span><b>${v}</b></div>`).join("");

  const top = ops
    .filter((o) => isNum(o.multiplier) && !["ZAKONSKI OGRANIČENO", "UVJETI ZABRANJUJU", "OTKAZANO"].includes(o.verdict))
    .sort((a, b) => b.multiplier - a.multiplier).slice(0, 10);
  const ceilings = ops.filter((o) => isNum(o.max_buy)).sort((a, b) => b.max_buy - a.max_buy).slice(0, 10);
  if (top.length < 3 && ceilings.length) {
    $("#chartCard").hidden = false;
    $("#chartCard h3").innerHTML = 'Do koje nominalne cijene se isplati kupiti <span class="muted small">(cilj ROI ≥ 30 %, iz cijena na preprodaji)</span>';
    barChart("chartTop", ceilings.map((o) => ({
      label: `${o.event.artist} · ${o.event.city || o.event.country} ${dateFmt(o.event.date).slice(0, 6)}`,
      value: o.max_buy,
      tooltip: `<b>${esc(o.event.artist)}</b><br>${esc(o.location)} · ${esc(dateFmt(o.event.date))}<br>`
        + `Kupi do ${esc(eur(o.max_buy))} · granica ${esc(eur(o.breakeven_buy))}<br>Realna prodajna ~${esc(eur(o.expected_resale))} · potražnja ${esc(score(o.demand.score))}/100`,
      onClick: () => openDetail(o),
    })), { fmt: (v) => eur(v), tick: (t) => eur(t), title: "Kupi najviše do" });
    $("#resultsCard").hidden = !ops.length;
    renderResults();
    return;
  }
  $("#chartCard h3").innerHTML = 'Najveći očekivani skok cijene <span class="muted small">(očekivana prodajna ÷ nominalna, samo dopuštena tržišta)</span>';
  $("#chartCard").hidden = !top.length;
  barChart("chartTop", top.map((o) => ({
    label: `${o.event.artist} · ${o.event.city || o.event.country}`,
    value: o.multiplier,
    tooltip: `<b>${esc(o.event.artist)}</b><br>${esc(o.location)} · ${esc(dateFmt(o.event.date))}<br>`
      + `Očekivano ${esc(mult(o.multiplier))} (${esc(eur(o.face_ref))} → ${esc(eur(o.expected_resale))})<br>`
      + `Oček. ROI ${esc(pct(o.roi))} · potražnja ${esc(score(o.demand.score))}/100 · ${esc(o.verdict)}`,
    onClick: () => openDetail(o),
  })), { fmt: mult, ref: 1, refLabel: "×1 = nominalna cijena", tick: (t) => "×" + t, title: "Najveći očekivani skok cijene" });

  $("#resultsCard").hidden = !ops.length;
  renderResults();
}
const COLS = [
  { k: "verdict", l: "Preporuka", v: (o) => o.verdict, h: (o) => pill(o.verdict) },
  { k: "date", l: "Datum", v: (o) => o.event.date, h: (o) => esc(dateFmt(o.event.date)) },
  { k: "artist", l: "Izvođač", v: (o) => o.event.artist, h: (o) => `<b>${esc(o.event.artist)}</b>` },
  { k: "loc", l: "Mjesto", v: (o) => o.location, h: (o) => esc(o.location) },
  { k: "phase", l: "Faza", v: (o) => o.phase, h: (o) => esc(o.phase === "NAJAVA" && o.days_to_onsale != null ? `prodaja za ${o.days_to_onsale} d` : o.phase.toLowerCase()) },
  { k: "face", l: "Nomin.", n: 1, v: (o) => o.face_ref ?? o.max_buy, h: (o) => (o.face_ref == null && isNum(o.max_buy)
    ? `<span class="muted" title="Nominalna cijena nije poznata – kupnja se isplati do ovog iznosa">≤ ${eur(o.max_buy)}</span>` : eur(o.face_ref)) },
  { k: "resale", l: "Oček. prodaja", n: 1, v: (o) => o.expected_resale, h: (o) => eur(o.expected_resale) },
  { k: "mult", l: "×", n: 1, v: (o) => o.multiplier, h: (o) => mult(o.multiplier) },
  { k: "profit", l: "Dobit*", n: 1, v: (o) => o.profit, h: (o) => eur(o.profit) },
  { k: "roi", l: "Oček. ROI", n: 1, v: (o) => o.roi, h: (o) => pct(o.roi) },
  { k: "demand", l: "Potražnja", n: 1, v: (o) => o.demand.score, h: (o) => `<span class="meter"><i style="width:${Math.round(o.demand.score * 100)}%"></i></span>${score(o.demand.score)}` },
  { k: "risk", l: "Rizik", n: 1, v: (o) => o.risk, h: (o) => score(o.risk) },
  { k: "qty", l: "Kom", n: 1, v: (o) => o.suggested_qty, h: (o) => o.suggested_qty || "–" },
  { k: "platform", l: "Platforma", v: (o) => (o.best ? o.best.name : ""), h: (o) => esc(o.best ? o.best.name : "—") },
];
function renderResults() {
  const ops = state.scan ? state.scan.opportunities : [];
  const counts = {};
  ops.forEach((o) => (counts[o.verdict] = (counts[o.verdict] || 0) + 1));
  const order = ["SVE", "KUPI", "RAZMOTRI", "PROVJERI CIJENU", "RASPRODANO", "PRESKOČI", "ZAKONSKI OGRANIČENO", "UVJETI ZABRANJUJU", "NEMA CIJENE", "OTKAZANO"];
  $("#verdictChips").innerHTML = order.filter((v) => v === "SVE" || counts[v])
    .map((v) => `<button type="button" class="chip${state.filter === v ? " active" : ""}" data-f="${esc(v)}">${esc(v === "SVE" ? "Sve" : v)} <span class="muted">${v === "SVE" ? ops.length : counts[v]}</span></button>`).join("");
  $$("#verdictChips .chip").forEach((c) => c.addEventListener("click", () => { state.filter = c.dataset.f; renderResults(); }));

  let rows = ops.filter((o) => (state.filter === "SVE" || o.verdict === state.filter)
    && (!state.search || `${o.event.artist} ${o.location}`.toLowerCase().includes(state.search)));
  if (state.sort.k) {
    const col = COLS.find((c) => c.k === state.sort.k);
    rows = rows.slice().sort((a, b) => {
      const x = col.v(a), y = col.v(b);
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "number" ? x - y : String(x).localeCompare(String(y), "hr")) * state.sort.dir;
    });
  }
  const t = $("#resultsTable");
  t.innerHTML = `<thead><tr><th class="num">#</th>${COLS.map((c) => `<th data-k="${c.k}" class="${c.n ? "num" : ""}">${esc(c.l)}${state.sort.k === c.k ? (state.sort.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>`
    + `<tbody>${rows.map((o, i) => `<tr data-id="${esc(o.event.id)}" tabindex="0"><td class="num">${i + 1}</td>${COLS.map((c) => `<td class="${c.n ? "num" : ""}">${c.h(o)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  $$("th[data-k]", t).forEach((th) => th.addEventListener("click", () => {
    state.sort = { k: th.dataset.k, dir: state.sort.k === th.dataset.k ? -state.sort.dir : (COLS.find((c) => c.k === th.dataset.k).n ? -1 : 1) };
    renderResults();
  }));
  $$("tbody tr", t).forEach((tr) => {
    const op = ops.find((o) => o.event.id === tr.dataset.id);
    tr.addEventListener("click", () => openDetail(op));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") openDetail(op); });
  });
}

/* ------------------------------------------------------------------ detalji + plan + kalendar */
function timeline(op) {
  const e = op.event;
  const now = new Date();
  const items = [];
  const forbidden = ["ZAKONSKI OGRANIČENO", "UVJETI ZABRANJUJU"].includes(op.verdict);
  const ownUse = forbidden ? " (samo za vlastiti odlazak)" : "";
  (e.presales || []).forEach((p) => p.start && items.push({ d: parseIso(p.start), cls: "buy", t: `Presale „${p.name}” – kupnja${ownUse}`, timed: true }));
  if (e.public_onsale) items.push({ d: parseIso(e.public_onsale), cls: "buy", t: forbidden ? `Javna prodaja${ownUse}` : "Javna prodaja – kupi u prvom satu", timed: true });
  const buyable = ["KUPI", "RAZMOTRI"].includes(op.verdict);
  if (op.phase === "U PRODAJI" && buyable) items.push({ d: now, cls: "buy", t: "Danas: ulaznice su u prodaji – kupi ako se slažeš s preporukom" });
  const firstSale = items.filter((i) => i.cls === "buy").map((i) => i.d).sort((a, b) => a - b)[0] || now;
  (op.advice.ladder || []).forEach((r) => {
    const d = r.iso ? parseIso(r.iso) : new Date(Math.max(firstSale.getTime(), now.getTime()));
    items.push({ d, cls: "sell", t: `Oglas: ${eur(r.price)} — ${r.label}` });
  });
  const ev = parseIso(e.date);
  const paysAfter = op.best && /nakon (održanog )?događaj/i.test(op.best.payout);
  const what = e.segment === "sport" ? "Utakmica" : "Koncert";
  items.push({ d: ev, cls: "event", t: `${what}${paysAfter ? ` · isplata (${op.best.name}) stiže tek nakon događaja` : ""}`, timed: true });
  items.sort((a, b) => a.d - b.d);
  const next = items.find((i) => i.d >= new Date(now.getTime() - 3600e3));
  if (next) next.next = true;
  return items;
}
function icsFor(op) {
  const fmtUtc = (d) => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00Z`;
  const fmtDay = (d) => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
  const icsText = (s) => String(s).replace(/\\/g, "\\\\").replace(/[,;]/g, (c) => "\\" + c).replace(/\n/g, "\\n");
  const stamp = fmtUtc(new Date());
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//karte//radar ulaznica//HR", "CALSCALE:GREGORIAN"];
  timeline(op).forEach((it, i) => {
    const uid = `${op.event.id}-${i}-${fmtDay(it.d)}@karte`;
    lines.push("BEGIN:VEVENT", `UID:${icsText(uid)}`, `DTSTAMP:${stamp}`);
    if (it.timed) lines.push(`DTSTART:${fmtUtc(it.d)}`, `DTEND:${fmtUtc(new Date(it.d.getTime() + 3600e3))}`);
    else lines.push(`DTSTART;VALUE=DATE:${fmtDay(it.d)}`);
    lines.push(`SUMMARY:${icsText(`${op.event.artist}: ${it.t}`)}`, `DESCRIPTION:${icsText(`${op.location}\n${op.advice.summary || ""}`)}`);
    if (it.cls === "buy") lines.push("BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", `DESCRIPTION:${icsText("Za 30 min počinje prodaja – uđi u red 10–15 min ranije")}`, "END:VALARM");
    lines.push("END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}
function detailHTML(op) {
  const e = op.event;
  const a = op.advice || {};
  const list = (arr, cls = "") => (arr && arr.length ? `<ul class="${cls}">${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : '<p class="muted">—</p>');
  const plat = (a.platforms || []).map((p) => `<tr><td>${esc(p.name)}</td><td class="num">${eur(p.list_price)}${p.capped ? " (limit)" : ""}</td><td class="num">${eur(p.net)}</td><td class="num">${nf0.format(p.p_sell * 100)} %</td><td class="num">${eur(p.ev)}</td></tr>`).join("");
  const tl = timeline(op).map((it) => `<li class="${it.cls}${it.next ? " next" : ""}"><span class="when">${esc(it.timed ? dtFmt(it.d.toISOString()) : dateFmt(it.d.toISOString()))}</span> ${esc(it.t)}${it.next ? " ← sljedeći korak" : ""}</li>`).join("");
  const share = isNum(op.listings_share) ? `<div class="metric"><span>Oglasa / kapacitet</span><b>${nf0.format(op.listings_share * 100)} %</b></div>` : "";
  const sec = e.secondary;
  const ceiling = op.face_ref == null && (isNum(op.max_buy) || isNum(op.breakeven_buy));
  const secText = sec && isNum(sec.lowest) ? `${nf0.format(sec.lowest)} ${esc(sec.currency)} <span class="muted small">${esc(sec.source)}${sec.observed ? ", " + esc(dateFmt(sec.observed)) : ""}</span>` : "—";
  const metrics = ceiling ? `
      <div class="metric"><span>Kupi najviše do</span><b>${eur(op.max_buy)}</b></div>
      <div class="metric"><span>Granica isplativosti</span><b>${eur(op.breakeven_buy)}</b></div>
      <div class="metric"><span>Najniža na preprodaji</span><b>${secText}</b></div>
      <div class="metric"><span>Realna prodajna (procjena)</span><b>${eur(op.expected_resale)}</b></div>
      <div class="metric"><span>Potražnja / rizik</span><b>${score(op.demand.score)} / ${score(op.risk)}</b></div>` : `
      <div class="metric"><span>Nominalna (ref.)</span><b>${eur(op.face_ref)}</b></div>
      <div class="metric"><span>Trošak s naknadama</span><b>${eur(op.buy_cost, 2)}</b></div>
      <div class="metric"><span>Očekivana prodajna</span><b>${eur(op.expected_resale)} <span class="muted">${mult(op.multiplier)}</span></b></div>
      <div class="metric"><span>Dobit ako se proda</span><b>${eur(op.profit)}</b></div>
      <div class="metric"><span>Očekivani ROI</span><b>${pct(op.roi)}</b></div>
      <div class="metric"><span>Potražnja / rizik</span><b>${score(op.demand.score)} / ${score(op.risk)}</b></div>
      <div class="metric"><span>Preporučeno komada</span><b>${op.suggested_qty || "–"}</b></div>${share}`;
  return `<div class="detail">
    <h2>${pill(op.verdict)} ${esc(e.name)}</h2>
    <div class="muted">${esc(op.location)} · ${esc(dtFmt(e.date))} · ${esc(op.phase)}</div>
    <p>${esc(a.summary || op.verdict_reason)}</p>
    <div class="metrics">${metrics}
    </div>
    ${op.face_ref == null ? '<div class="row"><button type="button" class="primary" data-act="calc">Upiši nominalnu cijenu → izračun</button></div>' : ""}
    <p class="muted small">Izvor procjene: ${esc(op.multiplier_source)} · pouzdanost ${score(op.demand.confidence)} %</p>
    <h3>Plan: kada kupiti i kada prodati</h3><ul class="timeline">${tl}</ul>
    <div class="cols"><div><h3>Kako kupiti</h3>${list(a.buy)}</div><div><h3>Kako i gdje prodati</h3>${list(a.sell)}</div></div>
    ${plat ? `<h3>Usporedba platformi (po ulaznici)</h3><div class="tablewrap"><table><thead><tr><th>Platforma</th><th class="num">Oglasna</th><th class="num">Neto</th><th class="num">P(prodaja)</th><th class="num">Oček. vrijednost</th></tr></thead><tbody>${plat}</tbody></table></div>` : ""}
    ${(a.safety || []).length ? `<h3>Sigurnosna provjera (bez kazni)</h3><ul class="safety">${a.safety.map((c) => `<li class="s-${esc(c.level)}">${esc(c.text)}</li>`).join("")}</ul>` : ""}
    <div class="cols"><div><h3>Rizici</h3>${list(a.risks, "flags")}</div><div><h3>Pravno</h3>${list(a.legal)}</div></div>
    <div class="actions">
      <button type="button" class="ghost" data-act="ics">📅 Kalendar (.ics)</button>
      <button type="button" class="ghost" data-act="cats">Analiziraj kategorije</button>
      <button type="button" class="ghost" data-act="journal">Dodaj u Moje prodaje</button>
      ${e.url ? `<a class="btn ghost" href="${esc(e.url)}" target="_blank" rel="noopener">Stranica događaja ↗</a>` : ""}
    </div></div>`;
}
function bindDetailActions(root, op) {
  $$("[data-act]", root).forEach((b) => b.addEventListener("click", () => {
    const act = b.dataset.act;
    if (act === "ics") saveBlob(new Blob([icsFor(op)], { type: "text/calendar" }), `${op.event.artist.replace(/[^\w-]+/g, "_")}.ics`);
    if (act === "cats") { closeDetail(); prefillCategories(op); showTab("cats"); }
    if (act === "calc") { closeDetail(); prefillCalc(op); showTab("calc"); }
    if (act === "journal") { closeDetail(); prefillJournal(op); showTab("journal"); }
  }));
}
function openDetail(op) {
  const body = $("#detailBody");
  body.innerHTML = detailHTML(op);
  bindDetailActions(body, op);
  $("#detail").showModal();
}
function closeDetail() { $("#detail").close(); }

/* ------------------------------------------------------------------ KALKULATOR */
function initCalc() {
  buildFields($("#calcFields"), eventFields());
  buildTags($("#calcTags"));
  $("#calcForm").addEventListener("submit", (e) => {
    e.preventDefault();
    busy($("#calcForm button[type=submit]"), async () => {
      const body = readFields($("#calcFields"), $("#calcTags"));
      body.seller_country = $("#sellerSel").value;
      const r = await api.post("/api/calc", body);
      const box = $("#calcResult");
      box.innerHTML = `<div class="card">${detailHTML(r.opportunity)}</div>`;
      bindDetailActions(box, r.opportunity);
      box.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  $("#calcExample").addEventListener("click", () => {
    const d = new Date(Date.now() + 120 * 864e5).toISOString().slice(0, 10);
    fillFields($("#calcFields"), { artist: "Primjer Izvođač", venue: "Arena Zagreb", city: "Zagreb", country: "HR", date: d, face: 59, face_max: 129,
      currency: "EUR", resale_lowest: 140, listing_count: 60, listeners: 1500000, vendor: "eventim", personalized: "ne" }, $("#calcTags"));
    $$("#calcTags input").forEach((c) => (c.checked = c.value === "first_visit"));
  });
}

function prefillCalc(op) {
  const e = op.event;
  fillFields($("#calcFields"), { segment: e.segment || "music", sport: e.sport || "football", league: e.league || "", name: e.name,
    artist: e.artist, venue: e.venue, city: e.city, country: e.country, region: e.region || "", date: (e.date || "").slice(0, 10),
    currency: "EUR", face: "", face_max: "", resale_lowest: op.secondary_lowest_eur ?? "", listing_count: e.secondary && e.secondary.listing_count || "",
    listeners: e.artist_listeners || "", fans: e.artist_fans || "", capacity: e.capacity || "", ticket_limit: e.ticket_limit || "",
    vendor: e.primary_vendor || "", personalized: e.personalized === true ? "da" : e.personalized === false ? "ne" : "" }, $("#calcTags"));
  $$("#calcTags input").forEach((c) => (c.checked = (e.tags || []).includes(c.value)));
  $("#calcResult").innerHTML = "";
  const field = $("#calcFields [name=face]");
  if (field) setTimeout(() => field.focus(), 50);
  toast(isNum(op.max_buy) ? `Upiši nominalnu cijenu (EUR). Isplati se do ~${eur(op.max_buy)}.` : "Upiši nominalnu cijenu (EUR) i klikni Izračunaj.");
}

/* ------------------------------------------------------------------ KATEGORIJE */
function catsEventFields() {
  const keep = ["segment", "artist", "name", "sport", "league", "venue", "city", "country", "region", "date", "currency", "listeners", "fans", "capacity", "ticket_limit", "vendor", "personalized", "budget"];
  return eventFields().filter((f) => keep.includes(f.k));
}
function addCatRow(c = {}) {
  const kinds = Object.entries(state.meta.kinds).map(([k, l]) => `<option value="${k}"${(c.kind || "standard") === k ? " selected" : ""}>${esc(l)}</option>`).join("");
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><input name="name" value="${esc(c.name || "")}" placeholder="npr. Parter"></td><td><select name="kind">${kinds}</select></td>
    <td><input name="face" type="number" step="0.01" value="${esc(c.face ?? "")}"></td><td><input name="resale_lowest" type="number" step="0.01" value="${esc(c.resale_lowest ?? "")}" placeholder="opcionalno"></td>
    <td><input name="listing_count" type="number" value="${esc(c.listing_count ?? "")}" placeholder="opc."></td><td><button type="button" class="ghost small" aria-label="Ukloni">✕</button></td>`;
  $("button", tr).addEventListener("click", () => tr.remove());
  $("#catsTable tbody").appendChild(tr);
}
function catsExample() {
  $("#catsTable tbody").innerHTML = "";
  [["Parter (stajanje)", "parter", 59], ["Tribina A – donji prsten", "standard", 79], ["Tribina B – gornji prsten", "tribina", 49], ["VIP paket", "vip", 189], ["Zaklonjeni pogled", "zaklonjeno", 39]]
    .forEach(([name, kind, face]) => addCatRow({ name, kind, face }));
}
function initCats() {
  buildFields($("#catsFields"), catsEventFields());
  buildTags($("#catsTags"));
  catsExample();
  fillFields($("#catsFields"), { artist: "Primjer Izvođač", venue: "Arena Zagreb", city: "Zagreb", country: "HR", date: new Date(Date.now() + 120 * 864e5).toISOString().slice(0, 10), listeners: 2000000, vendor: "eventim" });
  $("#addCat").addEventListener("click", () => addCatRow());
  $("#catsExample").addEventListener("click", catsExample);
  $("#catsForm").addEventListener("submit", (e) => {
    e.preventDefault();
    busy($("#catsForm button[type=submit]"), async () => {
      const event = readFields($("#catsFields"), $("#catsTags"));
      event.seller_country = $("#sellerSel").value;
      const cats = $$("#catsTable tbody tr").map((tr) => Object.fromEntries($$("input,select", tr).map((i) => [i.name, i.value])));
      renderCats(await api.post("/api/categories", { event, categories: cats }));
    });
  });
}
function prefillCategories(op) {
  const e = op.event;
  fillFields($("#catsFields"), { segment: e.segment || "music", sport: e.sport || "football", league: e.league || "", name: e.name,
    artist: e.artist, venue: e.venue, city: e.city, country: e.country, region: e.region || "", date: (e.date || "").slice(0, 10),
    currency: e.currency, listeners: e.artist_listeners || "", fans: e.artist_fans || "", capacity: e.capacity || "", ticket_limit: e.ticket_limit || "", vendor: e.primary_vendor || "",
    personalized: e.personalized === true ? "da" : e.personalized === false ? "ne" : "" }, $("#catsTags"));
  $$("#catsTags input").forEach((c) => (c.checked = (e.tags || []).includes(c.value)));
  $("#catsTable tbody").innerHTML = "";
  if (e.face_min != null) addCatRow({ name: "Najjeftinija kategorija", kind: "standard", face: e.face_min });
  if (e.face_max != null && e.face_max !== e.face_min) addCatRow({ name: "Najskuplja kategorija", kind: "vip", face: e.face_max });
  addCatRow({ name: "Parter (stajanje)", kind: "parter" });
  toast("Dodaj stvarne kategorije i cijene s cjenika pa klikni Izračunaj.");
}
function renderCats(r) {
  const rows = r.rows || [];
  const box = $("#catsResult");
  if (!rows.length) { box.innerHTML = `<div class="card"><p>${esc(r.summary)}</p></div>`; return; }
  box.innerHTML = `<div class="card"><h2>Rezultat</h2><p><b>${esc(r.summary)}</b></p>
    <h3>Očekivani ROI po kategoriji</h3><div id="catsChart"></div>
    <div class="tablewrap"><table><thead><tr><th>Kategorija</th><th>Vrsta</th><th class="num">Nominalna (€)</th><th class="num">Trošak</th><th class="num">Oček. prodaja</th><th class="num">×</th>
    <th class="num">Neto</th><th class="num">Dobit*</th><th class="num">P(prodaja)</th><th class="num">Oček. vrijednost</th><th class="num">Oček. ROI</th><th>Preporuka</th><th class="num">Kapital za par</th></tr></thead><tbody>
    ${rows.map((x) => `<tr><td>${x.best_roi ? "★ " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.kind_label)}</td><td class="num">${eur(x.face_eur)}</td><td class="num">${eur(x.buy_cost, 2)}</td>
      <td class="num">${eur(x.expected_resale)}</td><td class="num">${mult(x.multiplier)}</td><td class="num">${eur(x.net)}</td><td class="num">${eur(x.profit)}</td>
      <td class="num">${isNum(x.p_sell) ? nf0.format(x.p_sell * 100) + " %" : "—"}</td><td class="num">${eur(x.expected_value)}</td><td class="num">${pct(x.roi)}</td><td>${pill(x.verdict)}</td><td class="num">${eur(x.pair_capital)}</td></tr>`).join("")}
    </tbody></table></div><p class="muted small">★ = najbolji očekivani povrat. Dobit* = neto po ulaznici ako se proda. Procjena po kategoriji: ${esc(rows[0].multiplier_source)}.</p></div>`;
  barChart("catsChart", rows.filter((x) => isNum(x.roi)).map((x) => ({
    label: x.name, value: x.roi,
    tooltip: `<b>${esc(x.name)}</b> (${esc(x.kind_label)})<br>${esc(eur(x.face_eur))} → ${esc(eur(x.expected_resale))} · ${esc(mult(x.multiplier))}<br>Oček. vrijednost ${esc(eur(x.expected_value))} po ulaznici`,
  })), { fmt: pct, diverging: true, tick: (t) => nf0.format(t * 100) + " %", title: "ROI po kategoriji" });
}

/* ------------------------------------------------------------------ MOJE PRODAJE */
function journalFields() {
  return [
    { k: "artist", l: "Izvođač", req: true }, { k: "event_name", l: "Naziv koncerta" }, { k: "venue", l: "Dvorana" }, { k: "city", l: "Grad" },
    { k: "country", l: "Država", t: "country", def: "HR" }, { k: "event_date", l: "Datum koncerta", t: "date" }, { k: "category", l: "Kategorija / sektor" },
    { k: "qty", l: "Broj ulaznica", t: "number", def: 2 }, { k: "face_value", l: "Nominalna po ulaznici (€)", t: "number", step: "0.01" },
    { k: "buy_price", l: "Plaćeno po ulaznici s naknadama (€)", t: "number", step: "0.01" }, { k: "buy_date", l: "Datum kupnje", t: "date" },
    { k: "platform", l: "Platforma prodaje", t: "datalist", opts: state.meta.platforms.concat(["Njuškalo", "Facebook"]) },
    { k: "status", l: "Status", t: "select", opts: Object.entries(state.meta.statuses) },
    { k: "list_price", l: "Oglasna cijena po ulaznici (€)", t: "number", step: "0.01" }, { k: "sold_qty", l: "Prodano komada", t: "number" },
    { k: "sell_net", l: "Primljeno po ulaznici nakon naknada (€)", t: "number", step: "0.01" }, { k: "sell_date", l: "Datum prodaje", t: "date" },
    { k: "predicted_multiplier", l: "Procjena modela (×)", t: "number", step: "0.01", ph: "popuni se iz kalkulatora" }, { k: "notes", l: "Bilješke" },
  ];
}
function initJournal() {
  buildFields($("#jFields"), journalFields());
  $("#jForm").addEventListener("submit", (e) => {
    e.preventDefault();
    busy($("#jForm button[type=submit]"), async () => {
      const body = readFields($("#jFields"));
      const id = $("#jForm [name=id]").value;
      if (id) body.id = id;
      state.journal = await api.post("/api/journal", body);
      resetJournalForm();
      renderJournal();
      toast("Spremljeno.");
    });
  });
  $("#jReset").addEventListener("click", resetJournalForm);
  $("#jExample").addEventListener("click", () => {
    resetJournalForm();
    fillFields($("#jFields"), { artist: "A$AP Rocky", event_name: "A$AP Rocky – Arena Zagreb (prvi koncert u HR)", venue: "Arena Zagreb", city: "Zagreb",
      country: "HR", event_date: "2026-10-06", platform: "viagogo", status: "prodano", qty: 2, notes: "Prodano preko viagoga" });
    $("#jMsg").textContent = "Upiši svoje stvarne iznose: nominalnu, plaćeno, oglasnu cijenu, primljeno i datum prodaje – pa Spremi.";
    $("#jFields [name=face_value]").focus();
  });
  $("#jImport").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      state.journal = await api.post("/api/journal/import", { csv_text: await f.text() });
      renderJournal();
      toast(`Uvezeno: ${state.journal.imported}`);
    } catch (err) { toast("Greška: " + err.message); }
    e.target.value = "";
  });
}
function resetJournalForm() {
  $("#jForm").reset();
  $("#jForm [name=id]").value = "";
  $("#jFormTitle").textContent = "Nova transakcija";
  $("#jMsg").textContent = "";
  $("#jFields [name=qty]").value = 2;
}
function prefillJournal(op) {
  resetJournalForm();
  const e = op.event;
  fillFields($("#jFields"), { artist: e.artist, event_name: e.name, venue: e.venue, city: e.city, country: e.country, event_date: (e.date || "").slice(0, 10),
    qty: op.suggested_qty || 2, face_value: op.face_ref ? op.face_ref.toFixed(2) : "", buy_price: op.buy_cost ? op.buy_cost.toFixed(2) : "",
    buy_date: todayIso(), platform: op.best ? op.best.name : "viagogo", status: "kupljeno",
    predicted_multiplier: isNum(op.multiplier) ? op.multiplier.toFixed(2) : "" });
  $("#jMsg").textContent = "Provjeri iznose (stvarno plaćeno) i spremi. Procjena modela je spremljena radi kalibracije.";
}
async function loadJournal() {
  state.loaded.journal = true;
  try { state.journal = await api.get("/api/journal"); renderJournal(); }
  catch (e) { toast("Greška: " + e.message); }
}
function renderJournal() {
  const { trades, stats } = state.journal;
  $("#jKpis").innerHTML = [
    ["Uloženo ukupno", eur(stats.invested_total)], ["Prihod", eur(stats.revenue)], ["Ostvarena dobit", eur(stats.profit)],
    ["ROI (zatvoreno)", pct(stats.roi)], ["Kapital u igri", eur(stats.open_capital)],
    ["Uspješnost", isNum(stats.win_rate) ? nf0.format(stats.win_rate * 100) + " %" : "—"],
    ["Prodano prosj. dana prije koncerta", isNum(stats.avg_days_before_event) ? nf0.format(stats.avg_days_before_event) : "—"],
  ].map(([l, v]) => `<div class="kpi"><span>${l}</span><b>${v}</b></div>`).join("");
  const c = stats.calibration || {};
  $("#jCalib").innerHTML = `<h3 style="margin-top:0">Kalibracija modela tvojim prodajama</h3><p>${esc(c.message || "")}</p>`
    + (isNum(c.avg_realized_multiplier) ? `<p class="muted small">Prosječni ostvareni multiplikator: ${mult(c.avg_realized_multiplier)}${isNum(c.suggested_demand_slope) ? ` · prijedlog demand_slope ${c.suggested_demand_slope} (sada ${c.current_demand_slope})` : ""}</p>` : "");
  const closed = trades.filter((t) => isNum(t.realized_profit));
  $("#jChartCard").hidden = !closed.length;
  barChart("jChart", closed.slice(0, 15).map((t) => ({
    label: `${t.artist} · ${dateFmt(t.event_date)}`, value: t.realized_profit,
    tooltip: `<b>${esc(t.artist)}</b> · ${esc(t.platform)}<br>${esc(t.sold_qty)} kom · ROI ${esc(pct(t.roi))}${isNum(t.realized_multiplier) ? ` · ${esc(mult(t.realized_multiplier))}` : ""}`,
  })), { fmt: (v) => eur(v), diverging: true, tick: (t) => nf0.format(t) + " €", title: "Dobit po transakciji" });

  const t = $("#jTable");
  if (!trades.length) {
    t.innerHTML = `<tbody><tr><td class="muted">Još nema transakcija. Klikni „Primjer: A$AP Rocky (viagogo)” i upiši svoju prodaju.</td></tr></tbody>`;
  } else {
    t.innerHTML = `<thead><tr><th>Koncert</th><th>Status</th><th class="num">Kom</th><th class="num">Plaćeno/kom</th><th class="num">Primljeno/kom</th><th class="num">Dobit</th><th class="num">ROI</th><th class="num">× ostvareno</th><th class="num">Dana prije</th><th>Platforma</th><th></th></tr></thead><tbody>`
      + trades.map((x) => `<tr data-id="${esc(x.id)}"><td><b>${esc(x.artist)}</b> <span class="muted small">${esc(dateFmt(x.event_date))}${x.category ? " · " + esc(x.category) : ""}</span></td>
        <td>${esc(x.status_label)}</td><td class="num">${x.sold_qty ? `${x.sold_qty}/` : ""}${x.qty}</td><td class="num">${eur(x.buy_price, 2)}</td><td class="num">${eur(x.sell_net, 2)}</td>
        <td class="num">${eur(x.realized_profit)}</td><td class="num">${pct(x.roi)}</td><td class="num">${mult(x.realized_multiplier)}</td><td class="num">${x.days_before_event ?? "—"}</td><td>${esc(x.platform)}</td>
        <td><button type="button" class="ghost small" data-edit aria-label="Uredi" title="Uredi">✎</button> <button type="button" class="ghost small" data-del aria-label="Obriši" title="Obriši">✕</button></td></tr>`).join("") + "</tbody>";
    $$("tbody tr", t).forEach((tr) => {
      const x = trades.find((y) => y.id === tr.dataset.id);
      if (!x) return;
      $("[data-edit]", tr).addEventListener("click", (e) => { e.stopPropagation(); editTrade(x); });
      $("[data-del]", tr).addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`Obrisati ${x.artist}?`)) return;
        state.journal = await api.del(`/api/journal/${encodeURIComponent(x.id)}`);
        renderJournal();
      });
      tr.addEventListener("click", () => editTrade(x));
    });
  }
  const plats = stats.platforms || [];
  $("#jPlatforms").innerHTML = plats.length ? `<h3>Po platformi</h3><div class="tablewrap"><table><thead><tr><th>Platforma</th><th class="num">Prodaja</th><th class="num">Dobit</th><th class="num">ROI</th><th class="num">Prosj. dana prije koncerta</th></tr></thead><tbody>`
    + plats.map((p) => `<tr><td>${esc(p.platform)}</td><td class="num">${p.count}</td><td class="num">${eur(p.profit)}</td><td class="num">${pct(p.roi)}</td><td class="num">${p.avg_days_before_event ?? "—"}</td></tr>`).join("") + "</tbody></table></div>" : "";
  $("#jPath").textContent = `Podaci se spremaju lokalno: ${state.meta.settings.journal_path}`;
}
function editTrade(x) {
  resetJournalForm();
  fillFields($("#jFields"), x);
  $("#jForm [name=id]").value = x.id;
  $("#jFormTitle").textContent = `Uredi: ${x.artist}`;
  $("#jForm").scrollIntoView({ behavior: "smooth" });
}

/* ------------------------------------------------------------------ TRŽIŠTA */
async function loadMarkets() {
  state.loaded.markets = true;
  const r = await api.get("/api/markets");
  const t = $("#mTable");
  t.innerHTML = `<thead><tr><th class="num">#</th><th>Država</th><th class="num">Ocjena</th><th class="num">Veličina</th><th class="num">Pristup iz HR</th><th>Ticketmaster</th><th>Koncerti</th><th>Nogomet</th></tr></thead><tbody>`
    + r.rows.map((m, i) => `<tr data-code="${esc(m.code)}"><td class="num">${i + 1}</td><td><b>${esc(m.name)}</b> <span class="muted">${esc(m.code)}</span></td>
      <td class="num"><span class="meter"><i style="width:${Math.min(100, Math.round(m.score * 200))}%"></i></span>${nf0.format(m.score * 100)}</td>
      <td class="num">${nf0.format(m.size * 100)}</td><td class="num">${nf0.format(m.access * 100)}</td><td>${esc(m.tm)}</td>
      <td>${esc(m.rule_label)}${m.planned ? ` <span class="muted">(+ najavljeno: ${esc(m.planned)})</span>` : ""}</td>
      <td>${m.football_rule === "none" ? "bez posebnih ograničenja" : `<span class="pill v-legal">${esc(m.football_label)}</span>`}</td></tr>`).join("") + "</tbody>";
  $$("tbody tr", t).forEach((tr) => tr.addEventListener("click", () => {
    const m = r.rows.find((x) => x.code === tr.dataset.code);
    $("#lawBox").innerHTML = `<div class="notice"><b>${esc(m.name)} (${esc(m.code)})</b> — ${esc(m.rule_label)}<p>${esc(m.law_summary)}</p>`
      + `<p><b>Nogomet:</b> ${esc(m.football_label)} — ${esc(m.football_summary)}</p>${m.access_note ? `<p class="muted">${esc(m.access_note)}</p>` : ""}</div>`;
    $("#lawBox").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }));
  $("#lawBtn").addEventListener("click", showLaw);
  $("#lawCode").addEventListener("keydown", (e) => { if (e.key === "Enter") showLaw(); });
}
async function showLaw() {
  const code = $("#lawCode").value.trim();
  if (!code) return;
  const l = await api.get(`/api/laws?code=${encodeURIComponent(code)}`);
  const src = (l.sources || []).map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(new URL(u).hostname)}</a>`).join(" · ");
  $("#lawBox").innerHTML = `<div class="notice"><b>${esc(l.name || l.code)} (${esc(l.code)})</b><p>${esc(l.summary)}</p>${src ? `<p class="small">Izvori: ${src}</p>` : ""}</div>`;
}

/* ------------------------------------------------------------------ VODIČI */
async function loadGuides() {
  state.loaded.guides = true;
  const r = await api.get("/api/guides");
  state.guides = r.guides;
  $("#guideNav").innerHTML = r.guides.map((g, i) => `<button type="button" data-i="${i}" class="ghost${i === 0 ? " active" : ""}">${esc(g.title)}</button>`).join("");
  $$("#guideNav button").forEach((b) => b.addEventListener("click", () => {
    $$("#guideNav button").forEach((x) => x.classList.toggle("active", x === b));
    $("#guideBody").innerHTML = state.guides[+b.dataset.i].html; // HTML je escapean na serveru
    $("#guideBody").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  if (r.guides.length) $("#guideBody").innerHTML = r.guides[0].html;
}

/* ------------------------------------------------------------------ start */
async function init() {
  initTheme();
  try { state.meta = await api.get("/api/meta"); }
  catch (e) { document.body.insertAdjacentHTML("afterbegin", `<div class="notice warn">Ne mogu se spojiti na server: ${esc(e.message)}</div>`); return; }
  const m = state.meta;
  $("#version").textContent = ` v${m.version}`;
  $("#keys").innerHTML = [["Ticketmaster", m.settings.ticketmaster], ["SerpApi", m.settings.serpapi], ["PredictHQ", m.settings.predicthq],
    ["SeatGeek", m.settings.seatgeek], ["Last.fm", m.settings.lastfm]]
    .map(([n, on]) => `<span class="key ${on ? "on" : "off"}" title="${on ? "Ključ postavljen" : "Nema ključa u .env"}">${n}</span>`).join("")
    + `<span class="key on" title="Deezer i Wikipedia rade bez ključa">Deezer · Wikipedia</span>`;
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("#detailClose").addEventListener("click", closeDetail);
  $("#detail").addEventListener("click", (e) => { if (e.target.id === "detail") closeDetail(); });
  initRadar();
  initCalc();
  initCats();
  initJournal();
  const tab = (location.hash || "#radar").slice(1);
  showTab(["radar", "calc", "cats", "journal", "markets", "guides"].includes(tab) ? tab : "radar");
  if (!(m.settings.live_sources || []).length) runScan(); // bez ključeva odmah prikaži snimku stvarnih događaja
}
document.addEventListener("DOMContentLoaded", init);
