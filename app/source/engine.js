/* BASELINE ENGINE: JavaScript port of the three Focus 1 baselines (Python
   baseline1_prelaunch.py, baseline2_space_normal.py, baseline3_recent.py) plus
   the Focus 2 readiness rule. Same settings, same logic. Runs fully offline. */
const Engine = (() => {
  // (population mean, between-person SD, within-person daily SD, valid range): same as Python PRIORS
  const PRIORS = {
    resting_hr:     [72.1, 11.5, 3.0, [30, 200]],     // WESAD calm
    hrv_rmssd:      [47.4, 24.0, 7.0, [5, 250]],      // WESAD calm
    sleep_hours:    [6.8, 0.6, 0.6, [0, 14]],         // assumption
    reaction_ms:    [280.0, 25.0, 15.0, [120, 1500]], // assumption
    vision_score:   [1.65, 0.15, 0.10, [0, 2.5]],     // Starsight faint-vision score, logCS (higher = better); assumption
    mood:           [7.0, 1.0, 0.8, [1, 10]],         // assumption
    skin_temp:      [34.0, 0.6, 0.25, [25, 42]],      // WESAD chest
    breathing_rate: [16.2, 1.8, 0.8, [4, 60]],        // WESAD calm
    track_err_px:   [18.0, 5.0, 2.5, [0, 300]],       // Dockmaster laser tracking error (lower = better); assumption
    hearing_srt:    [-9.0, 2.0, 1.2, [-25, 15]],      // Comms Check speech-in-noise threshold, dB SNR (lower = better); assumption
  };
  const SIGNALS = [
    {key:'resting_hr', label:'Resting heart rate', unit:'bpm', source:'wearable'},
    {key:'hrv_rmssd', label:'HRV RMSSD', unit:'ms', source:'wearable'},
    {key:'breathing_rate', label:'Breathing rate', unit:'breaths/min', source:'wearable'},
    {key:'skin_temp', label:'Skin temperature', unit:'°C', source:'wearable'},
    {key:'sleep_hours', label:'Sleep duration', unit:'hours', source:'wearable'},
    {key:'reaction_ms', label:'Reaction time', unit:'ms', source:'game'},
    {key:'vision_score', label:'Faint vision', unit:'logCS', source:'game'},
    {key:'mood', label:'Mood', unit:'/10', source:'check-in'},
    {key:'track_err_px', label:'Hand-eye tracking error', unit:'px', source:'game'},
    {key:'hearing_srt', label:'Hearing in noise', unit:'dB SNR', source:'game'},
  ];
  // Baseline 1
  const MAD_TO_SD = 1.4826, EARTH_N0 = 10, FLATLINE_DAYS = 3;
  // Baseline 2
  const START_DAY = 15, WINDOW = 60, ACCEPT_Z = 3, MIN_DAYS_READY = 40, STABLE_LOOKBACK = 14,
        CENTER_TOL = 0.25, SCALE_TOL = 0.20, SHRINK_N0 = 10, DRIFT_WINDOW = 14, DRIFT_Z = 3, DRIFT_PERSIST = 5;
  // Baseline 3
  const RECENT_DAYS = 7, MIN_DAYS = 3, BLIP_Z = 3, REBASE_AFTER = 3, SUDDEN_Z = 3, SUDDEN_K = 2, SUDDEN_N = 3;
  // Focus 2 (from focus2_handover.py: one-way delay passes 5 min on day 152 of a minimum-energy Mars transfer)
  const HANDOVER_DEADLINE_DAY = 152;
  // Lights
  const DRIFTING_Z = 2;   // recent vs space normal beyond this = yellow "drifting"

  const ok = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
  const median = a => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

  const NO_FLATLINE = new Set(['reaction_ms', 'vision_score', 'mood', 'track_err_px', 'hearing_srt']); // game scores repeat naturally
  function clean(values, range, key) {
    const x = values.map(v => ok(v) ? Number(v) : NaN), reasons = x.map(v => Number.isFinite(v) ? '' : 'missing');
    x.forEach((v, i) => { if (Number.isFinite(v) && range && (v < range[0] || v > range[1])) { reasons[i] = 'impossible value'; x[i] = NaN; } });
    let i = 0;
    while (i < x.length) {
      let j = i;
      while (j + 1 < x.length && Number.isFinite(x[i]) && x[j + 1] === x[i]) j++;
      if (j - i + 1 >= FLATLINE_DAYS && !NO_FLATLINE.has(key)) for (let k = i; k <= j; k++) { reasons[k] = 'flatline (stuck sensor?)'; x[k] = NaN; }
      i = j + 1;
    }
    return {x, reasons};
  }

  /* Baseline 1: Earth normal from pre-launch days, blended with the population when days are few. */
  function fitEarth(values, key) {
    const [mu, between, within, range] = PRIORS[key];
    const good = clean(values, range, key).x.filter(Number.isFinite), n = good.length;
    if (!n) return {center: mu, scale: within, n: 0};
    const med = n >= 2 ? median(good) : good[0];
    let mad = n >= 2 ? median(good.map(v => Math.abs(v - med))) * MAD_TO_SD : within;
    if (!Number.isFinite(mad) || mad === 0) mad = within;
    const wc = n * between ** 2 / (n * between ** 2 + within ** 2), ws = n / (n + EARTH_N0);
    const center = wc * med + (1 - wc) * mu;
    const scale = Math.max(Math.sqrt(ws * mad ** 2 + (1 - ws) * within ** 2), 0.5 * within);
    return {center, scale, n};
  }

  function estimate(vals, within) {
    const n = vals.length, med = median(vals);
    let mad = n >= 2 ? median(vals.map(v => Math.abs(v - med))) * MAD_TO_SD : within;
    if (!Number.isFinite(mad) || mad === 0) mad = within;
    const w = n / (n + SHRINK_N0);
    return [med, Math.max(Math.sqrt(w * mad ** 2 + (1 - w) * within ** 2), 0.5 * within)];
  }

  /* Baseline 2: space normal. days = contiguous mission days, values aligned with them. */
  function spaceNormal(days, values, key) {
    const [, , within, range] = PRIORS[key];
    const {x, reasons} = clean(values, range, key);
    let learned = [], recentVals = [], center = NaN, scale = NaN, locked = false, lockDay = null, driftRun = 0;
    const hc = [], hs = [], out = [];
    days.forEach((day, t) => {
      const v = x[t];
      const z = Number.isFinite(v) && Number.isFinite(center) ? (v - center) / scale : NaN;
      let drift = false;
      if (Number.isFinite(v)) { recentVals.push(v); recentVals = recentVals.slice(-DRIFT_WINDOW); }
      if (locked && recentVals.length >= DRIFT_WINDOW / 2) {
        const se = 1.25 * scale * Math.sqrt(1 / recentVals.length + 1 / Math.max(learned.length, 1)) * 1.3;
        const zd = (median(recentVals) - center) / se;
        driftRun = Math.abs(zd) > DRIFT_Z ? driftRun + 1 : 0;
        drift = driftRun >= DRIFT_PERSIST;
      }
      let accepted = false;
      if (!locked && t >= START_DAY && Number.isFinite(v)) {
        const far = Number.isFinite(z) && learned.length >= 7 && Math.abs(z) > ACCEPT_Z;
        if (!far) { learned.push(v); learned = learned.slice(-WINDOW); accepted = true; }
      }
      if (!locked && learned.length >= 3) [center, scale] = estimate(learned, within);
      hc.push(center); hs.push(scale);
      let ready = false;
      if (hc.length > STABLE_LOOKBACK && Number.isFinite(hc[hc.length - STABLE_LOOKBACK - 1])) {
        const cOld = hc[hc.length - STABLE_LOOKBACK - 1], sOld = hs[hs.length - STABLE_LOOKBACK - 1];
        ready = learned.length >= MIN_DAYS_READY && Math.abs(center - cOld) / scale < CENTER_TOL && Math.abs(scale - sOld) / sOld < SCALE_TOL;
      }
      if (!locked && ready) { locked = true; lockDay = day; }
      out.push({day, t, value: x[t], reason: reasons[t], z, drift, learned: accepted, center, scale, goodDays: learned.length, locked});
    });
    return {rows: out, lockDay, firstDrift: out.find(r => r.drift)?.day ?? null};
  }

  /* Baseline 3: recent (7-day median, never including today; borrows the space-normal wobble). */
  function recent(values, key, scaleByDay) {
    const [, , within, range] = PRIORS[key];
    const {x} = clean(values, range, key);
    let win = [], offHist = [], farRun = 0, pending = [];
    return x.map((v, t) => {
      const scale = scaleByDay && Number.isFinite(scaleByDay[t]) ? scaleByDay[t] : within;
      const center = win.length >= MIN_DAYS ? median(win) : NaN;
      const eff = win.length ? scale * Math.sqrt(1 + 1.571 / win.length) : scale;
      const z = Number.isFinite(v) && Number.isFinite(center) ? (v - center) / eff : NaN;
      const blip = Number.isFinite(z) && Math.abs(z) > BLIP_Z;
      offHist.push(Number.isFinite(z) && Math.abs(z) > SUDDEN_Z); offHist = offHist.slice(-SUDDEN_N);
      const sudden = offHist.filter(Boolean).length >= SUDDEN_K;
      if (Number.isFinite(v)) {
        if (blip) { farRun++; pending.push(v); if (farRun >= REBASE_AFTER) { win.push(...pending); farRun = 0; pending = []; } }
        else { win.push(v); farRun = 0; pending = []; }
        win = win.slice(-RECENT_DAYS);
      }
      return {center, z, blip, sudden};
    });
  }

  /* Five lights. GREEN ok · YELLOW watch · RED act · BLUE learning (space normal not trusted yet, so checked
     against the Earth normal) · GREY no reliable data (missing, stuck or impossible reading). */
  const EARTH_FAR_Z = 3;
  function light(s, r, c, earth) {
    if (s.reason) return {light: 'grey', text: `No reliable data: ${s.reason}`};
    if (s.drift) return {light: 'red', text: 'Slow change: last 14 days have moved away from your space normal'};
    if (r.sudden) return {light: 'red', text: 'Sudden change: far from your recent days on 2 of the last 3 days'};
    if (r.blip) return {light: 'yellow', text: 'One-off: today is far from your recent days'};
    if (!s.locked) {
      const hasEarth = earth && earth.n > 0;
      if (hasEarth && Number.isFinite(c.recent_vs_earth) && Math.abs(c.recent_vs_earth) > EARTH_FAR_Z)
        return {light: 'yellow', text: 'Far from your Earth normal while your space normal is still learning'};
      const learning = s.t < START_DAY ? 'Settling in after launch' : (s.goodDays == null ? 'Learning your space normal' : `Learning your space normal (${s.goodDays}/${MIN_DAYS_READY} good days)`);
      return {light: 'blue', text: hasEarth ? `${learning}; checked against your Earth normal` : `${learning}; no Earth normal yet`};
    }
    if (Number.isFinite(c.recent_vs_space) && Math.abs(c.recent_vs_space) > DRIFTING_Z) return {light: 'yellow', text: 'Drifting: recent days differ from your space normal'};
    return {light: 'green', text: 'Within your space normal'};
  }
  const LIGHTS = {
    green:  {word: 'OK',       color: '#3d8f5f', meaning: 'Within your space normal'},
    yellow: {word: 'Watch',    color: '#d6a12c', meaning: 'A one-off day, recent days drifting, or far from Earth normal while learning'},
    red:    {word: 'Act',      color: '#c8463b', meaning: 'A sudden change, or a slow change over 14 days'},
    blue:   {word: 'Learning', color: '#5b8def', meaning: 'Space normal not trusted yet; checked against your Earth normal'},
    grey:   {word: 'No data',  color: '#a3a8b2', meaning: 'Missing, stuck or impossible reading: check the sensor'},
  };

  /* Full analysis for one astronaut. mission/prelaunch: arrays of records {day, signal keys...}. */
  function analyse(mission, prelaunch = []) {
    const daysPresent = mission.map(r => Number(r.day)).filter(Number.isFinite);
    if (!daysPresent.length) return null;
    const first = Math.min(...daysPresent), last = Math.max(...daysPresent);
    const days = Array.from({length: last - first + 1}, (_, i) => first + i);
    const byDay = new Map(mission.map(r => [Number(r.day), r]));
    const signals = {};
    for (const sig of SIGNALS) {
      const k = sig.key, values = days.map(d => byDay.get(d)?.[k]);
      const earth = fitEarth(prelaunch.map(r => r[k]), k);
      const sp = spaceNormal(days, values, k);
      const rc = recent(values, k, sp.rows.map(r => r.scale));
      const rows = sp.rows.map((s, t) => {
        const r = rc[t], w = Number.isFinite(s.scale) ? s.scale : earth.scale;
        const c = {
          today_vs_recent: r.z,
          recent_vs_space: (r.center - s.center) / w,
          space_vs_earth: (s.center - earth.center) / earth.scale,
          recent_vs_earth: (r.center - earth.center) / earth.scale,
          today_vs_earth: (s.value - earth.center) / earth.scale,
        };
        return {...s, raw: ok(values[t]) ? Number(values[t]) : NaN, recent: r.center, blip: r.blip, sudden: r.sudden, earth: earth.center, ...c, ...light(s, r, c, earth)};
      });
      const hasData = values.some(ok);
      signals[k] = {earth, rows, lockDay: sp.lockDay, firstDrift: sp.firstDrift, hasData};
    }
    // Focus 2 readiness: a signal counts 100% once locked, else up to 90% as it gathers good days.
    const used = SIGNALS.filter(s => signals[s.key].hasData).map(s => s.key);
    const readiness = days.map((d, t) => used.length ? used.reduce((a, k) => {
      const r = signals[k].rows[t]; return a + (r.locked ? 1 : Math.min(r.goodDays / MIN_DAYS_READY, 1) * 0.9);
    }, 0) / used.length : 0);
    const lockDays = used.map(k => signals[k].lockDay);
    const readyDay = used.length && lockDays.every(d => d !== null) ? Math.max(...lockDays) : null;
    const slowest = used.filter(k => signals[k].lockDay === null).concat(used.slice().sort((a, b) => (signals[b].lockDay ?? 1e9) - (signals[a].lockDay ?? 1e9)))[0] || null;
    return {days, signals, readiness, readyDay, slowest, used, deadline: HANDOVER_DEADLINE_DAY};
  }

  /* Demo crew: same recipe as the Python demo (baseline 2 + 3), 5 astronauts, 20 pre-launch + 200 mission days. */
  function demoCrew(ids) {
    let seed = 7;
    const rand = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
    const normal = () => Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
    const SETTLE = {resting_hr: -0.8, sleep_hours: -1.0, skin_temp: 0.8, breathing_rate: 0.6, reaction_ms: 0.3, mood: -0.3, hrv_rmssd: 0, vision_score: 0, track_err_px: 0.4, hearing_srt: 0};
    const ILL = {resting_hr: 1.0, hrv_rmssd: -1.0, sleep_hours: -0.7, reaction_ms: 0.8, mood: -0.8, skin_temp: 0.9, breathing_rate: 0.7, vision_score: 0, track_err_px: 0.7, hearing_srt: 0.3};
    const pre = {}, mis = {};
    ids.forEach((id, a) => {
      const own = Object.fromEntries(Object.entries(PRIORS).map(([k, p]) => [k, Math.min(p[3][1] - 4.5 * p[2], Math.max(p[3][0] + 4.5 * p[2], p[0] + normal() * p[1]))])); // keep each person's normal well inside the valid range
      pre[id] = []; mis[id] = [];
      for (let d = -20; d <= 200; d++) {
        if (d === 0) continue;
        const r = {astronaut: id, day: d};
        for (const [k, p] of Object.entries(PRIORS)) {
          const sd = p[2]; let v = own[k] + normal() * sd;
          if (d > 0) {
            v += SETTLE[k] * sd * (1 - Math.exp(-d / 4));
            if (a === 1 && d >= 35 && d < 40) v += ILL[k] * 2.5 * sd;                                    // AST-002 illness
            if (k === 'vision_score' && (a === 0 || a === 2) && d >= 110) v -= Math.min((d - 110) / 60, 1) * 3 * sd; // slow vision decline
            if (k === 'sleep_hours' && a === 3 && d === 100) v -= 3.5 * sd;                              // AST-004 one bad night
            if (k === 'sleep_hours' && a === 2 && d >= 120 && d <= 123) v -= 3 * sd;                     // AST-003 sleep crash
          }
          r[k] = Math.round(v * 100) / 100;
        }
        if (a === 4 && d >= 80 && d <= 83) r.skin_temp = 33.1;   // AST-005 stuck skin-temperature sensor
        if (a === 4 && d === 90) for (const k of Object.keys(PRIORS)) r[k] = null; // AST-005 missed day
        (d < 0 ? pre[id] : mis[id]).push(r);
      }
    });
    return {pre, mis};
  }

  return {light, LIGHTS, PRIORS, SIGNALS, START_DAY, MIN_DAYS_READY, HANDOVER_DEADLINE_DAY, clean, fitEarth, spaceNormal, recent, analyse, demoCrew};
})();
if (typeof module !== 'undefined') module.exports = Engine;
