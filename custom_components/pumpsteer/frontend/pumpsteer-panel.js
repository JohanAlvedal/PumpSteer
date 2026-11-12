/*
 * PumpSteer sidebar panel.
 *
 * Display only: reads PumpSteer entities, calls the normal number/switch
 * services for settings, and reads long-term statistics for the savings
 * chart. No build step, no external dependencies, fully local.
 */

const TEXT = {
  sv: {
    title: "PumpSteer",
    toPump: "Till värmepumpen",
    realOut: "Verklig ute",
    indoor: "Inomhus",
    target: "Mål",
    priceNow: "Elpris nu",
    outlook: "Väderutsikt",
    nightMin: "Natt min",
    next24: "Närmaste dygnet",
    cheap: "Billigt",
    normal: "Normalt",
    expensive: "Dyrt",
    plan: "Förväntad åtgärd",
    planBrake: "broms",
    planPreheat: "förvärmning möjlig",
    planNormal: "normal",
    noPlan: "Ingen prisplan ännu – väntar på nästa uppdatering.",
    why: "Varför?",
    savings: "Uppskattad besparing",
    savingsSub: "Värdet av att flytta värme från dyra till billiga timmar, jämfört med dagens snittpris",
    savedIn: "Sparat",
    perDay: "Snitt per dag",
    total: "Totalt sedan start",
    shifted: "Bromsad energi",
    d7: "7 d",
    d30: "30 d",
    year: "År",
    rangeName: { 7: "senaste 7 dagarna", 30: "senaste 30 dagarna", 365: "senaste året" },
    noStats: "Ingen statistik ännu. Home Assistant sammanställer den en gång i timmen.",
    perDayBar: "Per dag",
    perMonthBar: "Per månad",
    cumulative: "Ackumulerat",
    estimateNote: "Uppskattning, inte mätning. Justera kWh per °C och timme under integrationens alternativ.",
    settings: "Inställningar",
    aggressiveness: "Aggressivitet",
    aggrNames: ["Av – bara komfort", "Mycket försiktig", "Försiktig", "Balanserad", "Sparsam", "Max besparing"],
    preheat: "Förvärmning vid billig el",
    preheatSub: "Värm extra inför dyra perioder",
    holiday: "Semesterläge",
    holidaySub: "Lägre måltemperatur",
    targetTemp: "Måltemperatur",
    ramp: "Brake Ramp Time",
    rampSub: "Hur mjukt bromsen går in",
    status: "Status",
    updated: "Uppdaterad",
    learning: "Termisk inlärning",
    notFound: "Hittar inga PumpSteer-entiteter. Är integrationen laddad?",
    loading: "Laddar…",
    modes: {
      normal: "Normal", braking: "Bromsar", pre_braking: "Förbromsar", brake_hold: "Håller broms",
      preheating: "Förvärmer", precool: "Förkyler", summer_mode: "Sommarläge", holiday: "Semester",
      safe_mode: "Säkert läge", error: "Fel",
    },
  },
  en: {
    title: "PumpSteer",
    toPump: "Sent to heat pump",
    realOut: "Real outdoor",
    indoor: "Indoor",
    target: "Target",
    priceNow: "Price now",
    outlook: "Weather outlook",
    nightMin: "Night min",
    next24: "Next 24 hours",
    cheap: "Cheap",
    normal: "Normal",
    expensive: "Expensive",
    plan: "Expected action",
    planBrake: "brake",
    planPreheat: "preheat possible",
    planNormal: "normal",
    noPlan: "No price plan yet – waiting for the next update.",
    why: "Why?",
    savings: "Estimated savings",
    savingsSub: "Value of moving heat from expensive to cheap hours, versus today's mean price",
    savedIn: "Saved",
    perDay: "Average per day",
    total: "Total since start",
    shifted: "Braked energy",
    d7: "7 d",
    d30: "30 d",
    year: "Year",
    rangeName: { 7: "last 7 days", 30: "last 30 days", 365: "last year" },
    noStats: "No statistics yet. Home Assistant compiles them once per hour.",
    perDayBar: "Per day",
    perMonthBar: "Per month",
    cumulative: "Cumulative",
    estimateNote: "An estimate, not a measurement. Tune kWh per °C and hour in the integration options.",
    settings: "Settings",
    aggressiveness: "Aggressiveness",
    aggrNames: ["Off – comfort only", "Very gentle", "Gentle", "Balanced", "Saving", "Max saving"],
    preheat: "Preheat on cheap power",
    preheatSub: "Heat extra before expensive periods",
    holiday: "Holiday mode",
    holidaySub: "Lower target temperature",
    targetTemp: "Target temperature",
    ramp: "Brake Ramp Time",
    rampSub: "How softly the brake engages",
    status: "Status",
    updated: "Updated",
    learning: "Thermal learning",
    notFound: "No PumpSteer entities found. Is the integration loaded?",
    loading: "Loading…",
    modes: {
      normal: "Normal", braking: "Braking", pre_braking: "Pre-braking", brake_hold: "Holding brake",
      preheating: "Preheating", precool: "Precooling", summer_mode: "Summer mode", holiday: "Holiday",
      safe_mode: "Safe mode", error: "Error",
    },
  },
};

const CAT_COLOR = { cheap: "#4fa3ff", normal: "#8a929c", expensive: "#ff9f43" };
const MODE_COLOR = {
  braking: "#ff9f43", pre_braking: "#ff9f43", brake_hold: "#ff9f43", precool: "#ff9f43",
  preheating: "#4fa3ff", normal: "#3ecf8e", holiday: "#a78bfa",
  summer_mode: "#8a929c", safe_mode: "#ef5350", error: "#ef5350",
};
const SAVE_COLOR = "#3ecf8e";

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const num = (v) => {
  const n = typeof v === "number" ? v : parseFloat(v);
  return Number.isFinite(n) ? n : null;
};

class PumpSteerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = null;
    this._entryIndex = 0;
    this._range = 30;
    this._stats = null;
    this._statsKey = null;
    this._statsLoading = false;
    this._lastSig = null;
    this._raf = null;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._loadEntities();
    this._scheduleRender();
  }

  get hass() {
    return this._hass;
  }

  set narrow(v) {
    this._narrow = v;
    this._lastSig = null;
    this._scheduleRender();
  }

  set panel(v) {
    this._panel = v;
  }

  connectedCallback() {
    this._statsTimer = setInterval(() => {
      this._statsKey = null;
      this._scheduleRender();
    }, 10 * 60 * 1000);
  }

  disconnectedCallback() {
    clearInterval(this._statsTimer);
  }

  get _t() {
    const lang = (this._hass?.language || "en").toLowerCase();
    return lang.startsWith("sv") ? TEXT.sv : TEXT.en;
  }

  get _lang() {
    return this._hass?.locale?.language || this._hass?.language || "en";
  }

  async _loadEntities() {
    try {
      this._entries = await this._hass.callWS({ type: "pumpsteer/entities" });
    } catch (err) {
      console.error("PumpSteer: could not load entities", err);
      this._entries = [];
    }
    this._lastSig = null;
    this._scheduleRender();
  }

  get _ids() {
    return this._entries?.[this._entryIndex]?.entities || {};
  }

  _state(key) {
    const id = this._ids[key];
    return id ? this._hass.states[id] : undefined;
  }

  _scheduleRender() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => {
      this._raf = null;
      this._render();
    });
  }

  _signature() {
    // Re-render only when one of our entities changed (hass updates are frequent).
    const parts = Object.values(this._ids).map((id) => this._hass.states[id]?.last_updated || "");
    return [parts.join("|"), this._range, this._entryIndex, this._statsKey, this._narrow, !!this._stats].join("#");
  }

  async _loadStats() {
    const id = this._ids.savings;
    if (!id || this._statsLoading) return;
    const key = `${id}:${this._range}`;
    if (this._statsKey === key) return;
    this._statsLoading = true;
    const period = this._range === 365 ? "month" : "day";
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    if (this._range === 365) {
      start.setDate(1);
      start.setMonth(start.getMonth() - 11);
    } else {
      start.setDate(start.getDate() - (this._range - 1));
    }
    try {
      const res = await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        statistic_ids: [id],
        period,
        types: ["change"],
      });
      this._stats = (res?.[id] || []).map((r) => ({
        start: typeof r.start === "number" ? new Date(r.start) : new Date(r.start),
        change: num(r.change) ?? 0,
      }));
    } catch (err) {
      console.error("PumpSteer: statistics failed", err);
      this._stats = [];
    }
    this._statsKey = key;
    this._statsLoading = false;
    this._lastSig = null;
    this._scheduleRender();
  }

  _fmt(v, digits = 1) {
    const n = num(v);
    if (n === null) return "–";
    return n.toLocaleString(this._lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  _money(v, digits = 0) {
    const n = num(v);
    if (n === null) return "–";
    const cur = this._state("savings")?.attributes?.unit_of_measurement || "";
    return `${n.toLocaleString(this._lang, { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${esc(cur)}`.trim();
  }

  async _onClick(ev) {
    const el = ev.composedPath().find((n) => n.dataset && n.dataset.action);
    if (!el) return;
    const a = el.dataset.action;
    const hass = this._hass;
    try {
      if (a === "aggr") {
        await hass.callService("number", "set_value", { entity_id: this._ids.aggressiveness, value: Number(el.dataset.value) });
      } else if (a === "step") {
        const key = el.dataset.key;
        const st = this._state(key);
        const attrs = st?.attributes || {};
        const step = num(attrs.step) ?? 0.5;
        const cur = num(st?.state) ?? 0;
        let next = cur + step * Number(el.dataset.dir);
        if (num(attrs.min) !== null) next = Math.max(attrs.min, next);
        if (num(attrs.max) !== null) next = Math.min(attrs.max, next);
        await hass.callService("number", "set_value", { entity_id: this._ids[key], value: Math.round(next * 100) / 100 });
      } else if (a === "toggle") {
        await hass.callService("switch", "toggle", { entity_id: this._ids[el.dataset.key] });
      } else if (a === "range") {
        this._range = Number(el.dataset.value);
        this._stats = null;
        this._statsKey = null;
        this._scheduleRender();
      } else if (a === "entry") {
        this._entryIndex = Number(el.dataset.value);
        this._stats = null;
        this._statsKey = null;
        this._lastSig = null;
        this._scheduleRender();
      }
    } catch (err) {
      console.error("PumpSteer: action failed", err);
    }
  }

  _explain(mode, a) {
    const t = this._t;
    const sv = t === TEXT.sv;
    const unit = esc((a.current_price_unit || "").split("/")[0]);
    const price = `${this._fmt(a.current_price, 2)} ${unit}`.trim();
    const off = this._fmt(Math.abs(num(a.price_offset_c) ?? 0), 1);
    const min = num(a.minutes_until_expensive);
    const minTxt = min !== null ? `${Math.round(min)} min` : "";
    switch (mode) {
      case "braking":
        return sv
          ? `Elpriset (${price}) ligger över dagens P80 (${this._fmt(a.p80, 2)}). PumpSteer höjer signalen till värmepumpen med ${off}° så att den drar ner. Bromsen släpper om inne går under ${this._fmt(a.comfort_floor_c)}°.`
          : `The price (${price}) is above today's P80 (${this._fmt(a.p80, 2)}). PumpSteer raises the signal to the heat pump by ${off}° so it backs off. The brake releases if indoor drops below ${this._fmt(a.comfort_floor_c)}°.`;
      case "pre_braking":
        return sv
          ? `En dyr period börjar om ${minTxt}. Bromsen rampas in i förväg så att den är på plats när priset stiger.`
          : `An expensive period starts in ${minTxt}. The brake ramps in early so it is in place when the price rises.`;
      case "brake_hold":
        return sv
          ? `Kort billigare paus mellan två dyra perioder – bromsen hålls kvar i stället för att släppa och ta i igen.`
          : `Short cheaper gap between two expensive periods – the brake is held instead of releasing and re-engaging.`;
      case "preheating":
        return sv
          ? `Dyr el om ${minTxt} och kallt väder väntas. Huset värms ${this._fmt(a.preheat_boost_c)}° extra medan elen är billigare.`
          : `Expensive power in ${minTxt} and cold weather ahead. The house is heated ${this._fmt(a.preheat_boost_c)}° extra while power is cheaper.`;
      case "precool":
        return sv
          ? `Varmt väder väntas. Signalen höjs för att undvika övervärmning.`
          : `Warm weather ahead. The signal is raised to avoid overheating.`;
      case "summer_mode":
        return sv
          ? `Ute är varmare än sommargränsen – den riktiga utetemperaturen skickas oförändrad.`
          : `Outdoor is above the summer threshold – the real outdoor temperature is passed through.`;
      case "holiday":
        return sv ? `Semesterläge: lägre måltemperatur, annars samma prislogik.` : `Holiday mode: lower target, otherwise the same price logic.`;
      case "safe_mode":
      case "error":
        return sv
          ? `Säkert läge – optimeringen är pausad. ${esc(a.status || "")}`
          : `Safe mode – optimisation paused. ${esc(a.status || "")}`;
      default: {
        if (num(a.aggressiveness) === 0) {
          return sv ? `Prisstyrning avstängd (aggressivitet 0). PumpSteer håller bara inomhustemperaturen.` : `Price control off (aggressiveness 0). PumpSteer only holds the indoor temperature.`;
        }
        if ((num(a.price_offset_c) ?? 0) > 0.05) {
          return sv ? `Bromsen rampas ut mjukt efter en dyr period.` : `The brake is ramping out softly after an expensive period.`;
        }
        return sv
          ? `Normal drift. PumpSteer håller inne nära målet (${this._fmt(a.target_temperature)}°). Priset är ${t[a.price_category] ? t[a.price_category].toLowerCase() : "normalt"} just nu.`
          : `Normal operation. PumpSteer holds indoor near the target (${this._fmt(a.target_temperature)}°). Price is ${t[a.price_category] ? t[a.price_category].toLowerCase() : "normal"} right now.`;
      }
    }
  }

  _priceChart(a, preheatOn) {
    const t = this._t;
    const plan = Array.isArray(a.price_plan) ? a.price_plan : [];
    if (!plan.length) return `<div class="muted">${t.noPlan}</div>`;
    const max = Math.max(...plan.map((p) => num(p.price) ?? 0), 0.0001);
    const min = Math.min(...plan.map((p) => num(p.price) ?? 0), 0);
    const span = max - Math.min(min, 0) || 1;
    const bars = plan
      .map((p, i) => {
        const v = num(p.price) ?? 0;
        const h = Math.max(3, Math.round(((v - Math.min(min, 0)) / span) * 100));
        const tip = `${new Date(p.start).toLocaleTimeString(this._lang, { hour: "2-digit", minute: "2-digit" })} · ${this._fmt(v, 2)}`;
        return `<div class="bar" title="${esc(tip)}" style="height:${h}%;background:${CAT_COLOR[p.category] || CAT_COLOR.normal};opacity:${i === 0 ? 1 : 0.75}"></div>`;
      })
      .join("");
    const planRow = plan
      .map((p) => {
        const c = p.category === "expensive" ? MODE_COLOR.braking : p.category === "cheap" && preheatOn ? MODE_COLOR.preheating : "var(--ps-track)";
        return `<div class="seg" style="background:${c}"></div>`;
      })
      .join("");
    const labels = plan
      .map((p) => {
        const d = new Date(p.start);
        const show = d.getMinutes() === 0 && d.getHours() % 3 === 0;
        return `<div class="lbl">${show ? String(d.getHours()).padStart(2, "0") : ""}</div>`;
      })
      .join("");
    const cols = `grid-template-columns:repeat(${plan.length},minmax(0,1fr))`;
    return `
      <div class="chart" style="${cols}">${bars}</div>
      <div class="labels" style="${cols}">${labels}</div>
      <div class="small muted" style="margin:14px 0 6px">${t.plan}</div>
      <div class="planrow" style="${cols}">${planRow}</div>
      <div class="legend">
        <span><i style="background:${CAT_COLOR.cheap}"></i>${t.cheap}</span>
        <span><i style="background:${CAT_COLOR.normal}"></i>${t.normal}</span>
        <span><i style="background:${CAT_COLOR.expensive}"></i>${t.expensive}</span>
        <span class="sep"></span>
        <span><i style="background:${MODE_COLOR.braking}"></i>${t.planBrake}</span>
        <span><i style="background:${MODE_COLOR.preheating}"></i>${t.planPreheat}</span>
      </div>`;
  }

  _savingsSection() {
    const t = this._t;
    const sav = this._state("savings");
    if (!sav) return "";
    const attrs = sav.attributes || {};
    const ranges = [7, 30, 365]
      .map((r) => `<button class="seg-btn ${r === this._range ? "on" : ""}" data-action="range" data-value="${r}">${r === 7 ? t.d7 : r === 30 ? t.d30 : t.year}</button>`)
      .join("");
    let body;
    const stats = this._stats;
    if (!stats) {
      body = `<div class="muted">${t.loading}</div>`;
    } else if (!stats.length) {
      body = `<div class="muted">${t.noStats}</div>`;
    } else {
      const vals = stats.map((s) => s.change);
      const sum = vals.reduce((a, b) => a + b, 0);
      const days = this._range === 365 ? Math.max(1, Math.round((Date.now() - stats[0].start) / 86400000)) : Math.max(1, stats.length);
      const maxAbs = Math.max(...vals.map(Math.abs), 0.0001);
      const n = vals.length;
      let acc = 0;
      const cum = vals.map((v) => (acc += v));
      const cMax = Math.max(...cum, 0);
      const cMin = Math.min(...cum, 0);
      const cSpan = cMax - cMin || 1;
      const w = 1000 / n;
      const pts = cum.map((c, i) => `${(i * w + w / 2).toFixed(1)},${(100 - ((c - cMin) / cSpan) * 100).toFixed(1)}`).join(" ");
      const bars = vals
        .map((v, i) => {
          const h = Math.max(2, Math.round((Math.abs(v) / maxAbs) * 75));
          const label = stats[i].start.toLocaleDateString(this._lang, this._range === 365 ? { month: "short", year: "2-digit" } : { day: "numeric", month: "short" });
          return `<div class="bar" title="${esc(label)} · ${this._money(v, 2)}" style="height:${h}%;background:${v >= 0 ? SAVE_COLOR : "#ef5350"};opacity:.85"></div>`;
        })
        .join("");
      const gap = n > 60 ? 0 : 3;
      const first = stats[0].start.toLocaleDateString(this._lang, this._range === 365 ? { month: "short", year: "numeric" } : { day: "numeric", month: "short" });
      body = `
        <div class="tiles">
          <div class="tile"><div class="cap">${t.savedIn}, ${t.rangeName[this._range]}</div><div class="big" style="color:${SAVE_COLOR}">${this._money(sum)}</div></div>
          <div class="tile"><div class="cap">${t.perDay}</div><div class="big">${this._money(sum / days, 1)}</div></div>
          <div class="tile"><div class="cap">${t.total}</div><div class="big">${this._money(sav.state)}</div></div>
          <div class="tile"><div class="cap">${t.shifted}</div><div class="big">${this._fmt(attrs.reduced_kwh, 0)} kWh</div></div>
        </div>
        <div class="chart-wrap">
          <div class="chart" style="grid-template-columns:repeat(${n},minmax(0,1fr));gap:${gap}px;height:180px">${bars}</div>
          <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
            <polyline points="${pts}" fill="none" stroke="var(--primary-text-color)" stroke-width="2" stroke-dasharray="5 4" vector-effect="non-scaling-stroke"></polyline>
          </svg>
        </div>
        <div class="ends small muted"><span>${esc(first)}</span><span>${this._range === 365 ? "" : esc(new Date().toLocaleDateString(this._lang, { day: "numeric", month: "short" }))}</span></div>
        <div class="legend">
          <span><i style="background:${SAVE_COLOR}"></i>${this._range === 365 ? t.perMonthBar : t.perDayBar}</span>
          <span><i class="dash"></i>${t.cumulative}</span>
        </div>`;
    }
    return `
      <section class="card">
        <div class="row-head">
          <div><h2>${t.savings}</h2><div class="small muted">${t.savingsSub}</div></div>
          <div class="segs">${ranges}</div>
        </div>
        ${body}
        <div class="small muted note">${t.estimateNote}</div>
      </section>`;
  }

  _settings() {
    const t = this._t;
    const aggr = num(this._state("aggressiveness")?.state);
    const aggrBtns = [0, 1, 2, 3, 4, 5]
      .map((n) => `<button class="seg-btn big-btn ${aggr === n ? "on accent" : ""}" data-action="aggr" data-value="${n}" aria-label="${t.aggressiveness} ${n}">${n}</button>`)
      .join("");
    const sw = (key, label, sub) => {
      const st = this._state(key);
      if (!st) return "";
      const on = st.state === "on";
      return `<div class="set-row">
          <div><div class="lbl-main">${label}</div><div class="small muted">${sub}</div></div>
          <button class="switch ${on ? "on" : ""}" role="switch" aria-checked="${on}" aria-label="${label}" data-action="toggle" data-key="${key}"><span></span></button>
        </div>`;
    };
    const stepper = (key, label, sub, digits) => {
      const st = this._state(key);
      if (!st) return "";
      return `<div class="set-row">
          <div><div class="lbl-main">${label}</div><div class="small muted">${sub}</div></div>
          <div class="stepper">
            <button data-action="step" data-key="${key}" data-dir="-1" aria-label="−">−</button>
            <span>${this._fmt(st.state, digits)}</span>
            <button data-action="step" data-key="${key}" data-dir="1" aria-label="+">+</button>
          </div>
        </div>`;
    };
    return `
      <section class="card">
        <h2>${t.settings}</h2>
        ${this._state("aggressiveness") ? `
        <div class="set-block">
          <div class="row-head"><span class="lbl-main">${t.aggressiveness}</span><span class="small muted">${aggr !== null ? t.aggrNames[aggr] || "" : ""}</span></div>
          <div class="segs full">${aggrBtns}</div>
        </div>` : ""}
        ${stepper("target_temperature", t.targetTemp, t.indoor, 1)}
        ${sw("preheat", t.preheat, t.preheatSub)}
        ${sw("holiday", t.holiday, t.holidaySub)}
        ${stepper("house_inertia", t.ramp, t.rampSub, 1)}
      </section>`;
  }

  _render() {
    if (!this._hass) return;
    const t = this._t;
    if (this._entries === null) {
      this.shadowRoot.innerHTML = `${this._style()}<div class="page"><div class="muted">${t.loading}</div></div>`;
      return;
    }
    const ctrl = this._state("control");
    if (!ctrl) {
      this.shadowRoot.innerHTML = `${this._style()}<div class="page">${this._header(null)}<div class="card muted">${t.notFound}</div></div>`;
      return;
    }
    this._loadStats();
    const sig = this._signature();
    if (sig === this._lastSig) return;
    this._lastSig = sig;

    const a = ctrl.attributes || {};
    const mode = a.mode || "normal";
    const color = MODE_COLOR[mode] || MODE_COLOR.normal;
    const fake = num(ctrl.state);
    const out = num(a.outdoor_temperature);
    const indoor = num(a.indoor_temperature);
    const target = num(a.target_temperature);
    const outlook = this._state("outlook");
    const preheatOn = this._state("preheat")?.state === "on";
    const priceUnit = esc(a.current_price_unit || "");
    const catTxt = t[a.price_category] || "";
    const diff = (x, y) => (x !== null && y !== null ? `${x - y >= 0 ? "+" : "−"}${this._fmt(Math.abs(x - y))}°` : "");
    const updated = a.last_updated ? new Date(a.last_updated).toLocaleTimeString(this._lang, { hour: "2-digit", minute: "2-digit" }) : "–";

    const entryTabs =
      (this._entries || []).length > 1
        ? `<div class="segs">${this._entries.map((e, i) => `<button class="seg-btn ${i === this._entryIndex ? "on" : ""}" data-action="entry" data-value="${i}">${esc(e.title)}</button>`).join("")}</div>`
        : "";

    this.shadowRoot.innerHTML = `
      ${this._style()}
      <div class="page">
        ${this._header({ mode, color })}
        ${entryTabs}
        <div class="tiles kpis">
          <div class="card tile">
            <div class="cap">${t.toPump}</div>
            <div class="huge" style="color:${color}">${this._fmt(fake)}°</div>
            <div class="small muted">${t.realOut} ${this._fmt(out)}° · ${diff(fake, out)}</div>
          </div>
          <div class="card tile">
            <div class="cap">${t.indoor}</div>
            <div class="huge">${this._fmt(indoor)}°</div>
            <div class="small muted">${t.target} ${this._fmt(target)}° · ${diff(indoor, target)}</div>
          </div>
          <div class="card tile">
            <div class="cap">${t.priceNow}</div>
            <div class="huge">${this._fmt(a.current_price, 2)}<span class="unit"> ${priceUnit}</span></div>
            <div class="small" style="color:${CAT_COLOR[a.price_category] || "var(--secondary-text-color)"}">${catTxt} · P30 ${this._fmt(a.p30, 2)} / P80 ${this._fmt(a.p80, 2)}</div>
          </div>
          ${outlook ? `
          <div class="card tile">
            <div class="cap">${t.outlook}</div>
            <div class="huge">${this._fmt(outlook.attributes?.night_min_temp)}°</div>
            <div class="small muted">${t.nightMin} · ${esc(outlook.state)}</div>
          </div>` : ""}
        </div>

        <div class="layout">
          <main>
            <section class="card">
              <h2>${t.next24}</h2>
              ${this._priceChart(a, preheatOn)}
            </section>
            <section class="card why">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16h.01"></path></svg>
              <div><h2>${t.why}</h2><p>${this._explain(mode, a)}</p></div>
            </section>
            ${this._savingsSection()}
          </main>
          <aside>
            ${this._settings()}
            <section class="card">
              <h2>${t.status}</h2>
              <div class="stat-row"><span>${t.updated}</span><span>${updated}</span></div>
              <div class="stat-row"><span>Status</span><span>${esc(a.status || "–")}</span></div>
              <div class="stat-row"><span>${t.learning}</span><span>${this._fmt(a.thermal_confidence_percent, 0)} %</span></div>
            </section>
          </aside>
        </div>
      </div>`;

    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
  }

  _header(info) {
    const t = this._t;
    const pill = info
      ? `<div class="pill" style="color:${info.color};border-color:${info.color}"><span class="dot" style="background:${info.color}"></span>${esc(t.modes[info.mode] || info.mode)}</div>`
      : "";
    return `
      <header>
        <div class="title">
          ${this._narrow ? "<ha-menu-button></ha-menu-button>" : ""}
          <h1>${t.title}</h1>
        </div>
        ${pill}
      </header>`;
  }

  _style() {
    return `<style>
      :host {
        display: block;
        --ps-card: var(--card-background-color, #1c1f24);
        --ps-track: var(--secondary-background-color, #2a2e35);
        --ps-radius: var(--ha-card-border-radius, 14px);
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        min-height: 100vh;
        font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
      }
      * { box-sizing: border-box; }
      .page { max-width: 1360px; margin: 0 auto; padding: clamp(12px, 3vw, 32px); display: flex; flex-direction: column; gap: 16px; }
      header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
      .title { display: flex; align-items: center; gap: 8px; }
      h1 { margin: 0; font-size: 24px; font-weight: 600; }
      h2 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
      .pill { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 999px; border: 1px solid; font-weight: 600; font-size: 14px; }
      .dot { width: 8px; height: 8px; border-radius: 50%; }
      .card { background: var(--ps-card); border-radius: var(--ps-radius); padding: 18px; border: 1px solid var(--divider-color, transparent); box-shadow: var(--ha-card-box-shadow, none); }
      .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
      .kpis { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
      .tile .cap, .cap { font-size: 12px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .05em; }
      .huge { font-size: 36px; font-weight: 700; margin: 4px 0 2px; }
      .big { font-size: 26px; font-weight: 700; margin-top: 4px; }
      .unit { font-size: 15px; font-weight: 500; color: var(--secondary-text-color); }
      .small { font-size: 13px; }
      .muted { color: var(--secondary-text-color); }
      .layout { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }
      main { flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
      aside { flex: 1 1 300px; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
      .chart { display: grid; gap: 1px; align-items: end; height: 200px; }
      .chart .bar { border-radius: 3px 3px 1px 1px; min-width: 0; }
      .labels, .planrow { display: grid; gap: 1px; }
      .labels { margin-top: 6px; }
      .lbl { font-size: 11px; color: var(--secondary-text-color); overflow: visible; white-space: nowrap; }
      .planrow .seg { height: 10px; border-radius: 2px; }
      .legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 12px; font-size: 12px; color: var(--secondary-text-color); align-items: center; }
      .legend span { display: inline-flex; align-items: center; gap: 6px; }
      .legend i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
      .legend i.dash { width: 16px; height: 0; border-top: 2px dashed var(--primary-text-color); border-radius: 0; }
      .legend .sep { width: 1px; height: 12px; background: var(--divider-color); }
      .why { display: flex; gap: 12px; align-items: flex-start; }
      .why svg { flex: none; margin-top: 2px; color: var(--secondary-text-color); }
      .why h2 { margin-bottom: 4px; font-size: 15px; }
      .why p { margin: 0; line-height: 1.55; }
      .row-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 14px; }
      .row-head h2 { margin-bottom: 4px; }
      .segs { display: inline-flex; gap: 4px; background: var(--ps-track); padding: 4px; border-radius: 10px; flex-wrap: wrap; }
      .segs.full { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); width: 100%; }
      .seg-btn { border: none; background: transparent; color: var(--primary-text-color); font: inherit; font-size: 13px; font-weight: 600; min-width: 52px; height: 36px; border-radius: 7px; cursor: pointer; padding: 0 10px; }
      .seg-btn.on { background: var(--ps-card); }
      .seg-btn.on.accent { background: var(--primary-color); color: var(--text-primary-color, #fff); }
      .big-btn { height: 44px; font-size: 15px; min-width: 0; }
      .chart-wrap { position: relative; }
      .chart-wrap svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
      .ends { display: flex; justify-content: space-between; margin-top: 6px; }
      .note { margin-top: 12px; }
      .set-block { margin-bottom: 8px; }
      .set-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 56px; border-top: 1px solid var(--divider-color); padding: 6px 0; }
      .lbl-main { font-size: 14px; font-weight: 500; }
      .switch { flex: none; width: 52px; height: 30px; border-radius: 999px; border: none; padding: 3px; cursor: pointer; display: flex; justify-content: flex-start; background: var(--ps-track); }
      .switch.on { justify-content: flex-end; background: var(--primary-color); }
      .switch span { width: 24px; height: 24px; border-radius: 50%; background: #fff; display: block; }
      .stepper { display: flex; align-items: center; gap: 6px; }
      .stepper button { width: 44px; height: 44px; border: none; border-radius: 10px; background: var(--ps-track); color: var(--primary-text-color); font-size: 20px; cursor: pointer; }
      .stepper span { min-width: 48px; text-align: center; font-weight: 600; }
      .stat-row { display: flex; justify-content: space-between; gap: 12px; padding: 9px 0; border-top: 1px solid var(--divider-color); font-size: 14px; }
      .stat-row span:last-child { color: var(--secondary-text-color); text-align: right; overflow-wrap: anywhere; }
      button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    </style>`;
  }
}

if (!customElements.get("pumpsteer-panel")) {
  customElements.define("pumpsteer-panel", PumpSteerPanel);
}
