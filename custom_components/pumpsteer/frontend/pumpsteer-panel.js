/*
 * PumpSteer sidebar panel.
 *
 * Display only: reads PumpSteer entities, calls the normal number/switch
 * services for settings, and reads long-term statistics for the savings
 * chart. No build step, no external dependencies, fully local.
 */

// Mirrors settings.py (COMFORT_FLOOR_BY_AGGRESSIVENESS, PREHEAT_HEADROOM_BY_AGGRESSIVENESS,
// RAMP_SCALE, RAMP_MIN/MAX_MINUTES, RAMP_OUT_FACTOR, HOLIDAY_TEMP). Help text only.
const COMFORT_DROP = [0, 0.5, 1.0, 1.5, 2.0, 3.0];
const PREHEAT_HEADROOM = [0, 0.3, 0.5, 0.7, 1.0, 1.5];
const RAMP = { scale: 6, min: 15, max: 60, outFactor: 0.5 };
const HOLIDAY_TEMP = 17;

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
    collecting: "Samlar data – staplarna fylls på dag för dag. Besparing uppstår bara när PumpSteer bromsar eller förvärmer.",
    estimateNote: "Uppskattning, inte mätning. Justera kWh per °C och timme under integrationens alternativ.",
    settings: "Inställningar",
    aggressiveness: "Aggressivitet",
    aggrNames: ["Av – bara komfort", "Mycket försiktig", "Försiktig", "Balanserad", "Sparsam", "Max besparing"],
    preheat: "Förvärmning vid billig el",
    preheatSub: "Värm extra inför dyra perioder",
    holiday: "Semesterläge",
    holidaySub: "Lägre måltemperatur",
    targetTemp: "Måltemperatur",
    summer: "Sommargräns",
    cancel: "Avbryt",
    holidayOnTitle: "Slå på semesterläge?",
    holidayOnBtn: "Slå på",
    holidayOffTitle: "Stänga av semesterläge?",
    holidayOffBtn: "Stäng av",
    holidayOnText: `Måltemperaturen sänks till ${HOLIDAY_TEMP}° och huset blir kallare.`,
    holidayOnManual: "Inga datum är satta, så semesterläget gäller tills du stänger av det.",
    holidayOffText: "PumpSteer går tillbaka till din vanliga måltemperatur och värmer upp huset igen.",
    holidayPeriod: "Semesterperiod",
    holidayClears: "Semesterdatumen rensas också, så att läget inte slås på igen automatiskt.",
    holidayUntilOff: "Tills jag stänger av",
    holidayWithDates: "Välj datum",
    holidayStart: "Start",
    holidayEnd: "Slut",
    holidaySave: "Spara",
    holidayFuture: "Semesterläget slås på automatiskt vid start och av vid slut. Du får en notis båda gångerna.",
    errEnd: "Slutet måste vara efter starten och i framtiden.",
    errMissing: "Fyll i både start och slut.",
    summerSub: "Ute över detta = ingen styrning",
    helpLabel: "Förklaring",
    help: {
      aggressiveness: (n) =>
        n === 0
          ? "Nivå 0 stänger av all prisstyrning. PumpSteer håller bara innetemperaturen mot målet med PI-reglering."
          : `Hur hårt PumpSteer får spara. På nivå ${n} bromsar den vid dyr el men släpper bromsen om inne går under målet −${COMFORT_DROP[n].toLocaleString("sv")}°. Vid förvärmning får inne bli högst +${PREHEAT_HEADROOM[n].toLocaleString("sv")}° över målet. Högre nivå = större besparing men större temperatursvängningar.`,
      target_temperature: () =>
        "Innetemperaturen PumpSteer styr mot. PI-regulatorn justerar signalen till värmepumpen så att inne hamnar här, och både bromsens komfortgräns och förvärmningens tak räknas från detta värde.",
      preheat: () =>
        "När en dyr period närmar sig och väderprognosen visar kyla värmer PumpSteer huset lite extra medan elen är billigare. Huset lagrar värmen och klarar sedan bromsen bättre. Stängs av automatiskt om inne redan når taket för vald aggressivitet.",
      holiday: () =>
        `Sänker måltemperaturen till ${HOLIDAY_TEMP}° under semesterperioden (start och slut ställs in med PumpSteers datum-entiteter). Prislogiken fungerar som vanligt.`,
      house_inertia: (v) => {
        const rin = Math.max(RAMP.min, Math.min(RAMP.max, (v ?? 2) * RAMP.scale));
        const rout = Math.max(RAMP.min, rin * RAMP.outFactor);
        return `Hur mjukt bromsen går in och ut. Värde × ${RAMP.scale} = minuter för inrampning (${RAMP.min}–${RAMP.max} min). Nu: in på ${Math.round(rin)} min, ut på ${Math.round(rout)} min. Bromsen börjar också rampa in så långt före en dyr period. Tyngre hus (betong, golvvärme) tål ett högre värde.`;
      },
      summer_threshold: () =>
        "När den riktiga utetemperaturen är på eller över gränsen går PumpSteer i sommarläge och skickar den riktiga utetemperaturen vidare oförändrad. Ingen bromsning eller förvärmning sker.",
    },
    ramp: "Brake Ramp Time",
    rampSub: "Hur mjukt bromsen går in",
    status: "Status",
    updated: "Uppdaterad",
    learning: "Termisk inlärning",
    notFound: "Hittar inga PumpSteer-entiteter. Är integrationen laddad?",
    loading: "Laddar…",
    now: "Nu",
    history: "Komfort och styrning",
    historySub: "Innetemperatur mot mål – bakgrunden visar när PumpSteer bromsade eller förvärmde",
    braked: "Bromsade",
    preheated: "Förvärmde",
    lowestIndoor: "Lägsta inne",
    sIndoor: "Inne",
    sTarget: "Mål",
    sFake: "Till pumpen",
    sOutdoor: "Ute",
    noHist: "Ingen historik hittades för perioden.",
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
    collecting: "Collecting data – bars fill in day by day. Savings only accrue while PumpSteer brakes or preheats.",
    estimateNote: "An estimate, not a measurement. Tune kWh per °C and hour in the integration options.",
    settings: "Settings",
    aggressiveness: "Aggressiveness",
    aggrNames: ["Off – comfort only", "Very gentle", "Gentle", "Balanced", "Saving", "Max saving"],
    preheat: "Preheat on cheap power",
    preheatSub: "Heat extra before expensive periods",
    holiday: "Holiday mode",
    holidaySub: "Lower target temperature",
    targetTemp: "Target temperature",
    summer: "Summer threshold",
    cancel: "Cancel",
    holidayOnTitle: "Turn on holiday mode?",
    holidayOnBtn: "Turn on",
    holidayOffTitle: "Turn off holiday mode?",
    holidayOffBtn: "Turn off",
    holidayOnText: `The target temperature drops to ${HOLIDAY_TEMP}° and the house gets colder.`,
    holidayOnManual: "No dates are set, so holiday mode stays on until you turn it off.",
    holidayOffText: "PumpSteer returns to your normal target temperature and heats the house up again.",
    holidayPeriod: "Holiday period",
    holidayClears: "The holiday dates are cleared too, so the mode does not turn itself back on.",
    holidayUntilOff: "Until I turn it off",
    holidayWithDates: "Choose dates",
    holidayStart: "Start",
    holidayEnd: "End",
    holidaySave: "Save",
    holidayFuture: "Holiday mode turns on automatically at the start and off at the end. You get a notification both times.",
    errEnd: "The end must be after the start and in the future.",
    errMissing: "Fill in both start and end.",
    summerSub: "Outdoor above this = no control",
    helpLabel: "Explanation",
    help: {
      aggressiveness: (n) =>
        n === 0
          ? "Level 0 turns off all price control. PumpSteer only holds the indoor temperature at target with PI control."
          : `How hard PumpSteer may save. At level ${n} it brakes on expensive power but releases the brake if indoor drops below target −${COMFORT_DROP[n]}°. When preheating, indoor may rise at most +${PREHEAT_HEADROOM[n]}° above target. Higher level = more saving but larger temperature swings.`,
      target_temperature: () =>
        "The indoor temperature PumpSteer steers towards. The PI controller adjusts the signal to the heat pump so indoor ends up here; the brake's comfort floor and the preheat ceiling are both counted from this value.",
      preheat: () =>
        "When an expensive period is approaching and the forecast is cold, PumpSteer heats the house a little extra while power is cheaper. The house stores the heat and handles the brake better. Stops automatically when indoor reaches the ceiling for the chosen aggressiveness.",
      holiday: () =>
        `Lowers the target to ${HOLIDAY_TEMP}° during the holiday period (start and end are set with PumpSteer's date entities). Price logic works as usual.`,
      house_inertia: (v) => {
        const rin = Math.max(RAMP.min, Math.min(RAMP.max, (v ?? 2) * RAMP.scale));
        const rout = Math.max(RAMP.min, rin * RAMP.outFactor);
        return `How softly the brake engages and releases. Value × ${RAMP.scale} = ramp-in minutes (${RAMP.min}–${RAMP.max} min). Now: in over ${Math.round(rin)} min, out over ${Math.round(rout)} min. The brake also starts ramping in this long before an expensive period. Heavier houses (concrete, underfloor heating) tolerate a higher value.`;
      },
      summer_threshold: () =>
        "When the real outdoor temperature is at or above this threshold, PumpSteer enters summer mode and passes the real outdoor temperature through unchanged. No braking or preheating.",
    },
    ramp: "Brake Ramp Time",
    rampSub: "How softly the brake engages",
    status: "Status",
    updated: "Updated",
    learning: "Thermal learning",
    notFound: "No PumpSteer entities found. Is the integration loaded?",
    loading: "Loading…",
    now: "Now",
    history: "Comfort and control",
    historySub: "Indoor vs target – the background shows when PumpSteer braked or preheated",
    braked: "Braked",
    preheated: "Preheated",
    lowestIndoor: "Lowest indoor",
    sIndoor: "Indoor",
    sTarget: "Target",
    sFake: "Sent to pump",
    sOutdoor: "Outdoor",
    noHist: "No history found for this period.",
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

const PHASE = { braking: "braked", pre_braking: "braked", brake_hold: "braked", preheating: "preheated" };
const PHASE_COLOR = { braked: "rgba(255, 159, 67, 0.22)", preheated: "rgba(79, 163, 255, 0.22)" };

const toLocalInput = (d) => {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

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
    this._histHours = 24;
    this._helpOpen = new Set();
    this._confirm = null;
    this._onKey = (ev) => {
      if (ev.key === "Escape" && this._confirm) {
        this._confirm = null;
        this._scheduleRender();
      }
    };
    this._hist = null;
    this._histKey = null;
    this._histLoading = false;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("pointermove", (ev) => this._onHover(ev));
    this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onInput(ev));
    this.addEventListener("pointerleave", () => this._onHover(null));
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
    window.addEventListener("keydown", this._onKey);
    this._statsTimer = setInterval(() => {
      this._statsKey = null;
      this._histKey = null;
      this._scheduleRender();
    }, 5 * 60 * 1000);
  }

  disconnectedCallback() {
    window.removeEventListener("keydown", this._onKey);
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
    return [parts.join("|"), this._range, this._entryIndex, this._statsKey, this._narrow, !!this._stats, this._histHours, this._histKey, [...this._helpOpen].join(","), this._confirm ? this._confirm.key : ""].join("#");
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
    let n = num(v);
    if (n === null) return "–";
    if (Math.abs(n) < 0.5 * 10 ** -digits) n = 0; // avoid "−0,0"
    return n.toLocaleString(this._lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  _money(v, digits = 0) {
    const n = num(v);
    if (n === null) return "–";
    const cur = this._state("savings")?.attributes?.unit_of_measurement || "";
    return `${n.toLocaleString(this._lang, { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${esc(cur)}`.trim();
  }

  _time(d) {
    // 24 h clock unless the user explicitly chose 12 h in their HA profile.
    const h12 = this._hass?.locale?.time_format === "12";
    return new Date(d).toLocaleTimeString(this._lang, { hour: "2-digit", minute: "2-digit", hour12: h12 });
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
        const key = el.dataset.key;
        if (key === "holiday") {
          // Holiday mode changes comfort a lot: always ask first.
          const on = this._state(key)?.state !== "on";
          const dates = this._holidayDates();
          const start = new Date();
          start.setSeconds(0, 0);
          this._confirm = {
            key,
            on,
            useDates: !!dates,
            start: toLocalInput(dates ? dates.start : start),
            end: dates ? toLocalInput(dates.end) : "",
            error: "",
          };
          this._scheduleRender();
          return;
        }
        await hass.callService("switch", "toggle", { entity_id: this._ids[key] });
      } else if (a === "confirm-yes") {
        await this._confirmHoliday();
      } else if (a === "confirm-no") {
        if (ev.target !== el && el.classList.contains("modal-backdrop")) return; // click inside dialog
        this._confirm = null;
        this._scheduleRender();
      } else if (a === "range") {
        this._range = Number(el.dataset.value);
        this._stats = null;
        this._statsKey = null;
        this._scheduleRender();
      } else if (a === "help") {
        const k = el.dataset.key;
        if (this._helpOpen.has(k)) this._helpOpen.delete(k);
        else this._helpOpen.add(k);
        this._scheduleRender();
      } else if (a === "hist") {
        this._histHours = Number(el.dataset.value);
        this._hist = null;
        this._histKey = null;
        this._scheduleRender();
      } else if (a === "entry") {
        this._entryIndex = Number(el.dataset.value);
        this._stats = null;
        this._statsKey = null;
        this._hist = null;
        this._histKey = null;
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
        const tip = `${this._time(p.start)} · ${this._fmt(v, 2)}`;
        return `<div class="bar${i === 0 ? " now" : ""}" title="${esc(tip)}" style="height:${h}%;background:${CAT_COLOR[p.category] || CAT_COLOR.normal};opacity:${i === 0 ? 1 : 0.6}"></div>`;
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
    const t0 = new Date(plan[0].start).getTime();
    const slotMs = plan.length > 1 ? new Date(plan[1].start).getTime() - t0 : 3600000;
    const frac = Math.min(1, Math.max(0, (Date.now() - t0) / slotMs));
    const nowLeft = ((frac / plan.length) * 100).toFixed(3);
    return `
      <div class="chart-wrap">
        <div class="chart" style="${cols}">${bars}</div>
        <div class="nowline" style="left:${nowLeft}%"><span>${t.now} ${this._time(Date.now())}</span></div>
      </div>
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

  _savingsSlots() {
    // One slot per day (or month) in the selected range, so a fresh install
    // shows a single thin bar at the right instead of one huge block.
    const year = this._range === 365;
    const key = (d) => (year ? `${d.getFullYear()}-${d.getMonth()}` : `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`);
    const byKey = new Map();
    (this._stats || []).forEach((r) => {
      const k = key(r.start);
      byKey.set(k, (byKey.get(k) ?? 0) + r.change);
    });
    const slots = [];
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    if (year) d.setDate(1);
    const n = year ? 12 : this._range;
    for (let i = n - 1; i >= 0; i--) {
      const s = new Date(d);
      if (year) s.setMonth(s.getMonth() - i);
      else s.setDate(s.getDate() - i);
      slots.push({ start: s, value: byKey.has(key(s)) ? byKey.get(key(s)) : null });
    }
    return slots;
  }

  _moneyAuto(v) {
    const n = Math.abs(num(v) ?? 0);
    return this._money(v, n < 10 ? 2 : n < 100 ? 1 : 0);
  }

  _savingsSection() {
    const t = this._t;
    const sav = this._state("savings");
    if (!sav) return "";
    const attrs = sav.attributes || {};
    const cur = esc(attrs.unit_of_measurement || "");
    const ranges = [7, 30, 365]
      .map((r) => `<button class="seg-btn ${r === this._range ? "on" : ""}" data-action="range" data-value="${r}">${r === 7 ? t.d7 : r === 30 ? t.d30 : t.year}</button>`)
      .join("");
    const tiles = (sum, perDay) => `
      <div class="tiles">
        <div class="tile"><div class="cap">${t.savedIn}, ${t.rangeName[this._range]}</div><div class="big" style="color:${SAVE_COLOR}">${sum}</div></div>
        <div class="tile"><div class="cap">${t.perDay}</div><div class="big">${perDay}</div></div>
        <div class="tile"><div class="cap">${t.total}</div><div class="big">${this._moneyAuto(sav.state)}</div></div>
        <div class="tile"><div class="cap">${t.shifted}</div><div class="big">${this._fmt(attrs.reduced_kwh, num(attrs.reduced_kwh) < 10 ? 1 : 0)} kWh</div></div>
      </div>`;
    let body;
    if (!this._stats) {
      body = `<div class="muted">${t.loading}</div>`;
    } else {
      const year = this._range === 365;
      const slots = this._savingsSlots();
      const have = slots.filter((s) => s.value !== null);
      const sum = have.reduce((a, s) => a + s.value, 0);
      const days = year ? Math.max(1, have.length * 30.4) : Math.max(1, have.length);
      // Fixed minimum scale so near-zero days stay near zero instead of filling the chart.
      const minScale = year ? 10 : 1;
      const hi = Math.max(minScale, ...have.map((s) => s.value));
      const lo = Math.min(0, ...have.map((s) => s.value));
      const span = hi - lo;
      const Y = (v) => ((hi - v) / span) * 100; // % from top
      const zero = Y(0);
      const bars = slots
        .map((s) => {
          const label = s.start.toLocaleDateString(this._lang, year ? { month: "long", year: "numeric" } : { weekday: "short", day: "numeric", month: "short" });
          if (s.value === null) return `<div class="sb empty" title="${esc(label)}"></div>`;
          const top = Math.min(Y(s.value), zero);
          const h = Math.max(0.8, Math.abs(Y(s.value) - zero));
          const color = s.value >= 0 ? SAVE_COLOR : "#ef5350";
          return `<div class="sb" title="${esc(label)} · ${this._moneyAuto(s.value)}"><div style="top:${top.toFixed(2)}%;height:${h.toFixed(2)}%;background:${color}"></div></div>`;
        })
        .join("");
      const grid = [hi, hi / 2, 0];
      if (lo < 0) grid.push(lo);
      const gridHtml = grid
        .map((g) => `<div class="gl${g === 0 ? " zero" : ""}" style="top:${Y(g).toFixed(2)}%"><span>${this._fmt(g, hi < 10 ? 1 : 0)}</span></div>`)
        .join("");
      const step = year ? 1 : this._range <= 7 ? 1 : 5;
      const labels = slots
        .map((s, i) => {
          const isLast = i === slots.length - 1;
          const show = year || this._range <= 7 || isLast || (slots.length - 1 - i) % step === 0;
          const txt = year
            ? s.start.toLocaleDateString(this._lang, { month: "narrow" })
            : this._range <= 7
              ? s.start.toLocaleDateString(this._lang, { weekday: "short" })
              : String(s.start.getDate());
          return `<div>${show ? esc(txt) : ""}</div>`;
        })
        .join("");
      const cols = `grid-template-columns:repeat(${slots.length},minmax(0,1fr))`;
      const collecting = have.length < 2 ? `<div class="small muted collecting">${t.collecting}</div>` : "";
      body = `
        ${tiles(this._moneyAuto(sum), this._moneyAuto(sum / days))}
        ${collecting}
        <div class="sv-chart">
          <div class="sv-axis-unit small muted">${cur}</div>
          <div class="lc" style="height:180px">
            ${gridHtml}
            <div class="sv-bars" style="${cols}">${bars}</div>
          </div>
          <div class="sv-labels" style="${cols}">${labels}</div>
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

  async _loadHistory() {
    const id = this._ids.control;
    if (!id || this._histLoading) return;
    const key = `${id}:${this._histHours}`;
    if (this._histKey === key) return;
    this._histLoading = true;
    const t1 = Date.now();
    const t0 = t1 - this._histHours * 3600000;
    try {
      const res = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: new Date(t0).toISOString(),
        entity_ids: [id],
        minimal_response: false,
        no_attributes: false,
        significant_changes_only: false,
      });
      let lastA = {};
      let rows = (res?.[id] || [])
        .map((r) => {
          const a = r.a || lastA;
          lastA = a;
          const ts = r.lu ?? r.lc ?? r.last_updated;
          const t = typeof ts === "number" ? ts * 1000 : Date.parse(ts);
          return { t: Math.max(t, t0), s: num(r.s ?? r.state), a };
        })
        .filter((r) => Number.isFinite(r.t));
      // Keep the browser responsive: thin out dense data but keep every mode change.
      const maxRows = 1500;
      if (rows.length > maxRows) {
        const stride = Math.ceil(rows.length / maxRows);
        rows = rows.filter((r, i) => i % stride === 0 || i === rows.length - 1 || r.a.mode !== rows[i - 1]?.a.mode);
      }
      this._hist = { t0, t1, rows };
    } catch (err) {
      console.error("PumpSteer: history failed", err);
      this._hist = { t0, t1, rows: [] };
    }
    this._histKey = key;
    this._histLoading = false;
    this._lastSig = null;
    this._scheduleRender();
  }

  _ticks(t0, t1) {
    const hours = (t1 - t0) / 3600000;
    const step = hours <= 6 ? 1 : hours <= 24 ? 3 : 6;
    const out = [];
    const d = new Date(t0);
    d.setMinutes(0, 0, 0);
    d.setHours(d.getHours() + 1);
    for (; d.getTime() < t1; d.setHours(d.getHours() + 1)) {
      if (d.getHours() % step === 0) {
        out.push({ left: ((d.getTime() - t0) / (t1 - t0)) * 100, label: String(d.getHours()).padStart(2, "0") });
      }
    }
    return out;
  }

  _lineChart(series, { t0, t1, height = 150, fixed = null, unit = "", digits = 1, bands = "" }) {
    const vals = series.flatMap((s) => s.points.map((p) => p[1]).filter((v) => v !== null));
    if (!vals.length) return "";
    let lo = fixed ? fixed[0] : Math.min(...vals);
    let hi = fixed ? fixed[1] : Math.max(...vals);
    if (!fixed) {
      const pad = (hi - lo) * 0.08 || 0.5;
      lo -= pad;
      hi += pad;
    }
    const X = (t) => (((t - t0) / (t1 - t0)) * 1000).toFixed(1);
    const Y = (v) => (100 - ((v - lo) / (hi - lo)) * 100).toFixed(2);
    const paths = series
      .map((s) => {
        let d = "";
        let open = false;
        s.points.forEach(([t, v]) => {
          if (v === null) {
            open = false;
            return;
          }
          d += open ? ` H${X(t)} V${Y(v)}` : ` M${X(t)} ${Y(v)}`;
          open = true;
        });
        if (open) d += ` H1000`;
        return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" ${s.dash ? 'stroke-dasharray="6 4"' : ""} vector-effect="non-scaling-stroke"></path>`;
      })
      .join("");
    const grid = [hi, (hi + lo) / 2, lo];
    if (lo < 0 && hi > 0) {
      const near = (g) => Math.abs(g) / (hi - lo) < 0.12;
      for (let k = grid.length - 1; k >= 0; k--) if (near(grid[k])) grid.splice(k, 1);
      grid.push(0);
    }
    const gridHtml = grid
      .map((g) => `<div class="gl${g === 0 ? " zero" : ""}" style="top:${Y(g)}%"><span>${this._fmt(g, digits)}${unit}</span></div>`)
      .join("");
    const legend = series.map((s) => `<span><i class="${s.dash ? "dash" : ""}" style="${s.dash ? `border-color:${s.color}` : `background:${s.color}`}"></i>${s.name}</span>`).join("");
    return `
      <div class="lc" style="height:${height}px">
        ${bands}
        ${gridHtml}
        <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">${paths}</svg>
      </div>
      <div class="legend compact">${legend}</div>`;
  }

  _historySection() {
    const t = this._t;
    const hh = [24, 48]
      .map((h) => `<button class="seg-btn ${h === this._histHours ? "on" : ""}" data-action="hist" data-value="${h}">${h} h</button>`)
      .join("");
    const h = this._hist;
    let body;
    if (!h) {
      body = `<div class="muted">${t.loading}</div>`;
    } else if (!h.rows.length) {
      body = `<div class="muted">${t.noHist}</div>`;
    } else {
      const R = h.rows;
      const span = h.t1 - h.t0;
      // Group consecutive rows into control phases (braking, preheating, ...).
      const runs = [];
      R.forEach((r) => {
        const g = PHASE[r.a.mode] || null;
        const last = runs[runs.length - 1];
        if (last && last.g === g) return;
        if (last) last.end = r.t;
        runs.push({ g, start: r.t, end: h.t1 });
      });
      const hours = (g) => runs.filter((r) => r.g === g).reduce((acc, r) => acc + (r.end - r.start), 0) / 3600000;
      const bands = runs
        .filter((r) => r.g)
        .map((r) => {
          const left = ((r.start - h.t0) / span) * 100;
          const w = ((r.end - r.start) / span) * 100;
          const label = `${t[r.g]} ${this._time(r.start)}–${this._time(r.end)}`;
          return `<div class="phase" style="left:${left.toFixed(3)}%;width:${w.toFixed(3)}%;background:${PHASE_COLOR[r.g]}" title="${esc(label)}"></div>`;
        })
        .join("");
      const indoorVals = R.map((r) => num(r.a.indoor_temperature)).filter((v) => v !== null);
      const minIn = indoorVals.length ? Math.min(...indoorVals) : null;
      const chart = this._lineChart(
        [
          { name: t.sIndoor, color: "var(--primary-text-color)", points: R.map((r) => [r.t, num(r.a.indoor_temperature)]), width: 2.5 },
          { name: t.sTarget, color: "#3ecf8e", points: R.map((r) => [r.t, num(r.a.target_temperature)]), dash: true },
        ],
        { t0: h.t0, t1: h.t1, height: 220, unit: "°", bands }
      );
      const ticks = this._ticks(h.t0, h.t1)
        .map((k) => `<span style="left:${k.left.toFixed(2)}%">${k.label}</span>`)
        .join("");
      body = `
        <div class="hist-sum">
          <div><span class="dot" style="background:${MODE_COLOR.braking}"></span>${t.braked} <b>${this._fmt(hours("braked"), 1)} h</b></div>
          <div><span class="dot" style="background:${MODE_COLOR.preheating}"></span>${t.preheated} <b>${this._fmt(hours("preheated"), 1)} h</b></div>
          <div>${t.lowestIndoor} <b>${this._fmt(minIn)}°</b></div>
        </div>
        <div class="hov">
          ${chart.replace('<div class="legend compact">', `<div class="ticks">${ticks}</div><div class="legend compact">`)}
          <div class="cursor" hidden></div>
          <div class="readout" hidden></div>
        </div>`;
    }
    return `
      <section class="card">
        <div class="row-head">
          <div><h2>${t.history}</h2><div class="small muted">${t.historySub}</div></div>
          <div class="segs">${hh}</div>
        </div>
        ${body}
      </section>`;
  }

  _onHover(ev) {
    const box = ev && ev.composedPath().find((n) => n.classList && n.classList.contains("hov"));
    const root = this.shadowRoot.querySelector(".hov");
    if (!root) return;
    const cur = root.querySelector(".cursor");
    const out = root.querySelector(".readout");
    if (!box || !this._hist?.rows.length) {
      cur.hidden = true;
      out.hidden = true;
      return;
    }
    const rect = root.getBoundingClientRect();
    const AXIS = 40; // px reserved for the y-axis labels
    const f = Math.min(1, Math.max(0, (ev.clientX - rect.left - AXIS) / Math.max(1, rect.width - AXIS)));
    const { t0, t1, rows } = this._hist;
    const tt = t0 + f * (t1 - t0);
    let lo = 0;
    let hi = rows.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (rows[mid].t <= tt) lo = mid;
      else hi = mid - 1;
    }
    const r = rows[lo];
    const t = this._t;
    const a = r.a;
    cur.hidden = false;
    const x = AXIS + f * (rect.width - AXIS);
    cur.style.left = `${x.toFixed(1)}px`;
    out.hidden = false;
    out.style.left = f > 0.55 ? "auto" : `${(x + 10).toFixed(1)}px`;
    out.style.right = f > 0.55 ? `${(rect.width - x + 10).toFixed(1)}px` : "auto";
    out.innerHTML = `
      <b>${this._time(tt)} · ${esc(t.modes[a.mode] || a.mode || "")}</b>
      <div>${t.sIndoor} ${this._fmt(a.indoor_temperature)}° · ${t.sTarget} ${this._fmt(a.target_temperature)}°</div>
      <div>${t.sFake} ${this._fmt(r.s)}° · ${t.sOutdoor} ${this._fmt(a.outdoor_temperature)}°</div>
      <div>${t.priceNow} ${this._fmt(a.current_price, 2)}</div>`;
  }

  _holidayDates() {
    const dt = (key) => {
      const st = this._state(key);
      const d = st && !["unknown", "unavailable", ""].includes(st.state) ? new Date(st.state) : null;
      return d && !Number.isNaN(d.getTime()) && d.getFullYear() > 1970 ? d : null;
    };
    const start = dt("holiday_start");
    const end = dt("holiday_end");
    return start && end && end > start ? { start, end } : null;
  }

  _onInput(ev) {
    const el = ev.composedPath()[0];
    const field = el?.dataset?.field;
    if (!field || !this._confirm) return;
    if (field === "mode") {
      this._confirm.useDates = el.value === "dates";
      this._confirm.error = "";
      this._refreshDialog();
    } else {
      this._confirm[field] = el.value;
      if (this._confirm.error) {
        this._confirm.error = "";
        this.shadowRoot.querySelector(".modal .err")?.remove();
      }
    }
  }

  _refreshDialog() {
    const old = this.shadowRoot.querySelector(".modal-backdrop");
    if (old) old.remove();
    if (this._confirm) this.shadowRoot.querySelector(".page")?.insertAdjacentHTML("beforeend", this._confirmDialog());
  }

  async _confirmHoliday() {
    const c = this._confirm;
    if (!c) return;
    const hass = this._hass;
    const ids = this._ids;
    const setDt = (key, iso) => (ids[key] ? hass.callService("datetime", "set_value", { entity_id: ids[key], datetime: iso }) : null);
    const CLEARED = "1970-01-01T00:00:00+00:00"; // holiday.py treats 1970 as "no date"

    if (!c.on) {
      this._confirm = null;
      this._scheduleRender();
      await hass.callService("switch", "turn_off", { entity_id: ids.holiday });
      if (this._holidayDates()) await Promise.all([setDt("holiday_start", CLEARED), setDt("holiday_end", CLEARED)]);
      return;
    }

    if (!c.useDates) {
      this._confirm = null;
      this._scheduleRender();
      if (this._holidayDates()) await Promise.all([setDt("holiday_start", CLEARED), setDt("holiday_end", CLEARED)]);
      await hass.callService("switch", "turn_on", { entity_id: ids.holiday });
      return;
    }

    const start = c.start ? new Date(c.start) : null;
    const end = c.end ? new Date(c.end) : null;
    if (!start || !end || Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      c.error = this._t.errMissing;
      this._refreshDialog();
      return;
    }
    if (end <= start || end.getTime() <= Date.now()) {
      c.error = this._t.errEnd;
      this._refreshDialog();
      return;
    }
    this._confirm = null;
    this._scheduleRender();
    await Promise.all([setDt("holiday_start", start.toISOString()), setDt("holiday_end", end.toISOString())]);
    // Started already: switch on now. Future start: holiday.py turns it on at the start time.
    if (start.getTime() <= Date.now()) await hass.callService("switch", "turn_on", { entity_id: ids.holiday });
  }

  _confirmDialog() {
    const c = this._confirm;
    if (!c) return "";
    const t = this._t;
    const dates = this._holidayDates();
    const fmt = (d) => `${d.toLocaleDateString(this._lang, { day: "numeric", month: "short" })} ${this._time(d)}`;
    const canDates = !!(this._ids.holiday_start && this._ids.holiday_end);
    let body;
    let primary;
    if (!c.on) {
      const lines = [t.holidayOffText];
      if (dates) lines.push(`${t.holidayPeriod}: ${fmt(dates.start)} – ${fmt(dates.end)}`, t.holidayClears);
      body = lines.map((l) => `<p>${esc(l)}</p>`).join("");
      primary = t.holidayOffBtn;
    } else {
      const startFuture = c.useDates && c.start && new Date(c.start).getTime() > Date.now();
      const choice = canDates
        ? `<div class="radio-row" role="radiogroup">
            <label class="radio ${!c.useDates ? "on" : ""}"><input type="radio" name="ps-mode" value="manual" data-field="mode" ${!c.useDates ? "checked" : ""}>${t.holidayUntilOff}</label>
            <label class="radio ${c.useDates ? "on" : ""}"><input type="radio" name="ps-mode" value="dates" data-field="mode" ${c.useDates ? "checked" : ""}>${t.holidayWithDates}</label>
          </div>`
        : "";
      const fields = c.useDates
        ? `<div class="date-grid">
            <label>${t.holidayStart}<input type="datetime-local" data-field="start" value="${esc(c.start)}"></label>
            <label>${t.holidayEnd}<input type="datetime-local" data-field="end" value="${esc(c.end)}" min="${esc(c.start)}"></label>
          </div>
          <p>${esc(t.holidayFuture)}</p>`
        : `<p>${esc(t.holidayOnManual)}</p>`;
      body = `<p>${esc(t.holidayOnText)}</p>${choice}${fields}${c.error ? `<p class="err" role="alert">${esc(c.error)}</p>` : ""}`;
      primary = c.useDates && startFuture ? t.holidaySave : t.holidayOnBtn;
    }
    return `
      <div class="modal-backdrop" data-action="confirm-no">
        <div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="ps-dlg-title">
          <h2 id="ps-dlg-title">${c.on ? t.holidayOnTitle : t.holidayOffTitle}</h2>
          ${body}
          <div class="modal-actions">
            <button class="btn" data-action="confirm-no">${t.cancel}</button>
            <button class="btn primary" data-action="confirm-yes">${primary}</button>
          </div>
        </div>
      </div>`;
  }

  _helpBtn(key) {
    const open = this._helpOpen.has(key);
    return `<button class="help-btn ${open ? "on" : ""}" data-action="help" data-key="${key}" aria-expanded="${open}" aria-label="${this._t.helpLabel}">?</button>`;
  }

  _helpText(key, arg) {
    if (!this._helpOpen.has(key)) return "";
    const fn = this._t.help[key];
    return fn ? `<div class="help-text">${esc(fn(arg))}</div>` : "";
  }

  _settings() {
    const t = this._t;
    const aggr = num(this._state("aggressiveness")?.state);
    const aggrBtns = [0, 1, 2, 3, 4, 5]
      .map((n) => `<button class="seg-btn big-btn ${aggr === n ? "on accent" : ""}" data-action="aggr" data-value="${n}" aria-label="${t.aggressiveness} ${n}">${n}</button>`)
      .join("");
    const label = (key, main, sub) => `
      <div class="lbl-wrap">
        <div class="lbl-line"><span class="lbl-main">${main}</span>${this._helpBtn(key)}</div>
        ${sub ? `<div class="small muted">${sub}</div>` : ""}
      </div>`;
    const sw = (key, main, sub) => {
      const st = this._state(key);
      if (!st) return "";
      const on = st.state === "on";
      return `<div class="set-item"><div class="set-row">
          ${label(key, main, sub)}
          <button class="switch ${on ? "on" : ""}" role="switch" aria-checked="${on}" aria-label="${main}" data-action="toggle" data-key="${key}"><span></span></button>
        </div>${this._helpText(key)}</div>`;
    };
    const stepper = (key, main, sub, digits, unit = "") => {
      const st = this._state(key);
      if (!st) return "";
      return `<div class="set-item"><div class="set-row">
          ${label(key, main, sub)}
          <div class="stepper">
            <button data-action="step" data-key="${key}" data-dir="-1" aria-label="${main} −">−</button>
            <span>${this._fmt(st.state, digits)}${unit}</span>
            <button data-action="step" data-key="${key}" data-dir="1" aria-label="${main} +">+</button>
          </div>
        </div>${this._helpText(key, num(st.state))}</div>`;
    };
    return `
      <section class="card">
        <h2>${t.settings}</h2>
        ${this._state("aggressiveness") ? `
        <div class="set-block">
          <div class="row-head" style="margin-bottom:10px">
            <div class="lbl-line"><span class="lbl-main">${t.aggressiveness}</span>${this._helpBtn("aggressiveness")}</div>
            <span class="small muted">${aggr !== null ? t.aggrNames[aggr] || "" : ""}</span>
          </div>
          <div class="segs full">${aggrBtns}</div>
          ${this._helpText("aggressiveness", aggr ?? 0)}
        </div>` : ""}
        ${stepper("target_temperature", t.targetTemp, t.indoor, 1, "°")}
        ${sw("preheat", t.preheat, t.preheatSub)}
        ${sw("holiday", t.holiday, t.holidaySub)}
        ${stepper("house_inertia", t.ramp, t.rampSub, 1)}
        ${stepper("summer_threshold", t.summer, t.summerSub, 1, "°")}
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
    this._loadHistory();
    const sig = this._signature();
    if (sig === this._lastSig) return;
    if (this._confirm && this.shadowRoot.querySelector(".modal")) return; // keep the open dialog intact
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
    const updated = a.last_updated ? this._time(a.last_updated) : "–";

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
            ${this._historySection()}
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

    if (this._confirm) {
      this._refreshDialog();
      this.shadowRoot.querySelector('.modal [data-action="confirm-no"]')?.focus();
    }

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
      .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
      .kpis { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
      .tile .cap, .cap { font-size: 12px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .05em; }
      .huge { font-size: clamp(28px, 6vw, 36px); font-weight: 700; margin: 4px 0 2px; }
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
      .collecting { margin: 4px 0 10px; }
      .sv-chart { position: relative; margin-top: 30px; }
      .sv-axis-unit { position: absolute; top: -22px; left: 0; font-size: 11px; }
      .sv-bars { position: absolute; inset: 0; display: grid; gap: 3px; }
      .sb { position: relative; min-width: 0; max-width: 36px; width: 100%; justify-self: center; }
      .sb > div { position: absolute; left: 0; right: 0; border-radius: 3px; opacity: .9; }
      .sb:hover > div { opacity: 1; }
      .sv-labels { display: grid; gap: 3px; margin: 6px 0 0 40px; font-size: 11px; color: var(--secondary-text-color); text-align: center; white-space: nowrap; }
      .chart-wrap svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
      .note { margin-top: 12px; }
      .set-block { margin-bottom: 8px; }
      .set-item { border-top: 1px solid var(--divider-color); }
      .set-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 56px; padding: 6px 0; }
      .lbl-line { display: flex; align-items: center; gap: 6px; }
      .help-btn { flex: none; width: 22px; height: 22px; border-radius: 50%; border: 1px solid var(--divider-color); background: transparent; color: var(--secondary-text-color); font: inherit; font-size: 12px; font-weight: 700; cursor: pointer; padding: 0; line-height: 1; position: relative; }
      .help-btn::after { content: ""; position: absolute; inset: -11px; }
      .help-btn.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
      .help-text { font-size: 13px; line-height: 1.5; color: var(--secondary-text-color); background: var(--ps-track); border-radius: 8px; padding: 10px 12px; margin: 0 0 10px; }
      .set-block .help-text { margin-top: 10px; }
      .lbl-main { font-size: 14px; font-weight: 500; }
      .switch { flex: none; width: 52px; height: 30px; border-radius: 999px; border: none; padding: 3px; cursor: pointer; display: flex; justify-content: flex-start; background: var(--ps-track); }
      .switch.on { justify-content: flex-end; background: var(--primary-color); }
      .switch span { width: 24px; height: 24px; border-radius: 50%; background: #fff; display: block; }
      .stepper { display: flex; align-items: center; gap: 6px; }
      .stepper button { width: 44px; height: 44px; border: none; border-radius: 10px; background: var(--ps-track); color: var(--primary-text-color); font-size: 20px; cursor: pointer; }
      .stepper span { min-width: 48px; text-align: center; font-weight: 600; }
      .stat-row { display: flex; justify-content: space-between; gap: 12px; padding: 9px 0; border-top: 1px solid var(--divider-color); font-size: 14px; }
      .stat-row span:last-child { color: var(--secondary-text-color); text-align: right; overflow-wrap: anywhere; }
      .chart .bar.now { opacity: 1; animation: ps-pulse 1.6s ease-in-out infinite; box-shadow: 0 0 0 2px var(--primary-text-color); }
      @keyframes ps-pulse { 0%, 100% { filter: brightness(1); } 50% { filter: brightness(1.6); } }
      @media (prefers-reduced-motion: reduce) { .chart .bar.now { animation: none; } }
      .nowline { position: absolute; top: -18px; bottom: 0; width: 0; border-left: 2px solid var(--primary-text-color); pointer-events: none; }
      .nowline span { position: absolute; top: 0; left: 4px; font-size: 11px; font-weight: 600; white-space: nowrap; background: var(--ps-card); padding: 0 4px; border-radius: 4px; }
      section.card > .chart-wrap { margin-top: 22px; }
      .hov { position: relative; touch-action: pan-y; }
      .lc { position: relative; margin-left: 40px; }
      .lc svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
      .phase { position: absolute; top: 0; bottom: 0; }
      .hist-sum { display: flex; flex-wrap: wrap; gap: 8px 20px; font-size: 13px; color: var(--secondary-text-color); margin-bottom: 14px; }
      .hist-sum b { color: var(--primary-text-color); font-weight: 600; margin-left: 4px; }
      .hist-sum .dot { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
      .gl { position: absolute; left: 0; right: 0; border-top: 1px solid var(--divider-color); }
      .gl.zero { border-top: 1px solid var(--secondary-text-color); }
      .gl span { position: absolute; right: calc(100% + 6px); top: -8px; font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; }
      .legend.compact { margin: 8px 0 0 40px; gap: 12px; }
      .ticks { position: relative; height: 16px; margin: 6px 0 0 40px; }
      .ticks span { position: absolute; transform: translateX(-50%); font-size: 11px; color: var(--secondary-text-color); }
      .cursor { position: absolute; top: 0; bottom: 52px; width: 0; border-left: 1px dashed var(--primary-text-color); pointer-events: none; }
      .readout { position: absolute; top: 8px; z-index: 2; pointer-events: none; background: var(--ps-card); border: 1px solid var(--divider-color); border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.5; box-shadow: 0 4px 16px rgba(0,0,0,.25); white-space: nowrap; }
      .modal-backdrop { position: fixed; inset: 0; z-index: 10; background: rgba(0, 0, 0, .55); display: flex; align-items: center; justify-content: center; padding: 16px; }
      .modal { background: var(--ps-card); border: 1px solid var(--divider-color); border-radius: var(--ps-radius); padding: 22px; max-width: 420px; width: 100%; box-shadow: 0 12px 40px rgba(0, 0, 0, .4); }
      .modal h2 { font-size: 18px; margin: 0 0 10px; }
      .modal p { margin: 0 0 10px; line-height: 1.5; color: var(--secondary-text-color); font-size: 14px; }
      .radio-row { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; background: var(--ps-track); padding: 4px; border-radius: 10px; margin: 6px 0 12px; }
      .radio { display: flex; align-items: center; justify-content: center; min-height: 40px; border-radius: 7px; font-size: 14px; font-weight: 600; cursor: pointer; text-align: center; padding: 0 8px; }
      .radio input { position: absolute; opacity: 0; pointer-events: none; }
      .radio.on { background: var(--ps-card); }
      .radio:focus-within { outline: 2px solid var(--primary-color); outline-offset: 1px; }
      .date-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 10px; }
      .date-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
      .date-grid input { min-height: 44px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--ps-track); color: var(--primary-text-color); font: inherit; padding: 0 10px; color-scheme: dark light; }
      .modal .err { color: #ef5350; }
      .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
      .btn { min-height: 44px; padding: 0 18px; border-radius: 10px; border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); font: inherit; font-weight: 600; cursor: pointer; }
      .btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
      button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    </style>`;
  }
}

if (!customElements.get("pumpsteer-panel")) {
  customElements.define("pumpsteer-panel", PumpSteerPanel);
}
