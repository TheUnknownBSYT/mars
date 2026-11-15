/* =====================================================================
   MISSION PULSE GAMES: browser versions of ORBIT OPS, STARSIGHT and DOCKMASTER.
   Same rules, timings, scoring and readiness logic as the Python games
   (config.py / core/*.py / starsight_core.py). Graphics are simplified.
   Games.play(name, {history, checkin, quick, store}) -> Promise<result|null>
   ===================================================================== */
const Games = (() => {
  const rnd = (a, b) => a + Math.random() * (b - a);
  const rint = (a, b) => Math.floor(rnd(a, b + 1));
  const choice = a => a[Math.floor(Math.random() * a.length)];
  const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const median = v => { v = v.filter(x => x != null && Number.isFinite(x)).sort((a, b) => a - b); if (!v.length) return null; const m = v.length >> 1; return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2; };
  const mean = v => { v = v.filter(x => x != null && Number.isFinite(x)); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const sd = v => { v = v.filter(x => x != null); if (v.length < 2) return null; const m = mean(v); return Math.sqrt(v.reduce((a, x) => a + (x - m) ** 2, 0) / (v.length - 1)); };
  const R = (x, nd = 0) => x == null || !Number.isFinite(x) ? null : nd ? Math.round(x * 10 ** nd) / 10 ** nd : Math.round(x);
  const num = x => x == null || x === '' || !Number.isFinite(Number(x)) ? null : Number(x);
  const seeded = s => () => { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const COL = {bg: '#05070f', panel: '#0d1426', panel2: '#131d35', line: '#24315a', text: '#e8edfb', muted: '#8a96b6', dim: '#56617f',
    accent: '#4fd1ff', gold: '#ffd166', green: '#3ddc84', amber: '#ffb547', red: '#ff5d6c', orange: '#ff7b54', blue: '#4f8bff'};

  /* ------------------------------------------------------------------ stage
     A full-screen overlay. mode 'fixed' = 1280x720 logical canvas scaled to fit (like pygame SCALED);
     mode 'physical' = real CSS pixels (Starsight needs true sizes). */
  function stage(title, mode = 'fixed') {
    const el = document.createElement('div');
    el.className = 'game-overlay';
    el.innerHTML = `<div class="go-bar"><b>${title}</b><span class="go-status"></span><span class="go-prog"><i></i></span><button type="button" class="go-abort">Abort</button></div><canvas tabindex="0"></canvas>`;
    document.body.append(el);
    const cv = el.querySelector('canvas'), ctx = cv.getContext('2d');
    const s = {el, cv, ctx, mode, W: 1280, H: 720, scale: 1, ox: 0, oy: 0, mouse: {x: 640, y: 360}, handlers: {}, raf: 0, done: false};
    function fit() {
      const bw = window.innerWidth, bh = window.innerHeight - 48, dpr = window.devicePixelRatio || 1;
      if (mode === 'fixed') { s.scale = Math.min(bw / 1280, bh / 720); cv.style.width = 1280 * s.scale + 'px'; cv.style.height = 720 * s.scale + 'px'; cv.width = Math.round(1280 * s.scale * dpr); cv.height = Math.round(720 * s.scale * dpr); s.dpr = dpr; }
      else { s.W = bw; s.H = bh; cv.style.width = bw + 'px'; cv.style.height = bh + 'px'; cv.width = Math.round(bw * dpr); cv.height = Math.round(bh * dpr); s.dpr = dpr; s.scale = 1; }
    }
    fit(); window.addEventListener('resize', fit);
    const pos = e => { const r = cv.getBoundingClientRect(); return {x: (e.clientX - r.left) / (mode === 'fixed' ? s.scale : 1), y: (e.clientY - r.top) / (mode === 'fixed' ? s.scale : 1)}; };
    const on = (t, f) => { s.handlers[t] = f; };
    const keyH = e => { if (s.done) return; if (['Space', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.code)) e.preventDefault(); s.handlers.key && s.handlers.key(e.code, e.timeStamp, e); };
    const downH = e => { if (s.done) return; cv.focus(); const p = pos(e); s.mouse = p; s.handlers.down && s.handlers.down(p, e.timeStamp, e); };
    const upH = e => { if (s.done) return; s.handlers.up && s.handlers.up(pos(e), e.timeStamp, e); };
    const moveH = e => { s.mouse = pos(e); };
    window.addEventListener('keydown', keyH); cv.addEventListener('pointerdown', downH); window.addEventListener('pointerup', upH); window.addEventListener('pointermove', moveH);
    s.on = on;
    s.status = t => { el.querySelector('.go-status').textContent = t || ''; };
    s.progress = p => { el.querySelector('.go-prog i').style.width = Math.round(Math.max(0, Math.min(1, p)) * 100) + '%'; };
    s.begin = () => { const c = s.ctx; c.setTransform(s.dpr * s.scale, 0, 0, s.dpr * s.scale, 0, 0); return c; };
    s.loop = frame => new Promise(resolve => {
      s.finish = v => { if (s.done) return; s.done = true; cancelAnimationFrame(s.raf); window.removeEventListener('keydown', keyH); window.removeEventListener('pointerup', upH); window.removeEventListener('pointermove', moveH); window.removeEventListener('resize', fit); el.remove(); resolve(v); };
      el.querySelector('.go-abort').onclick = () => s.finish(null);
      const tick = t => { if (s.done) return; try { frame(t); } catch (err) { console.error(err); s.finish(null); return; } if (!s.done) s.raf = requestAnimationFrame(tick); };
      s.raf = requestAnimationFrame(tick); setTimeout(() => cv.focus(), 30);
    });
    return s;
  }
  function text(c, t, x, y, size = 20, color = COL.text, opts = {}) {
    c.font = `${opts.bold ? '700 ' : ''}${size}px ${opts.mono ? 'ui-monospace, Menlo, Consolas, monospace' : 'system-ui, -apple-system, Segoe UI, sans-serif'}`;
    c.fillStyle = color; c.textAlign = opts.align || 'center'; c.textBaseline = opts.base || 'middle'; c.fillText(t, x, y);
  }
  function wrapText(c, t, x, y, w, size, color, lh = 1.4) {
    c.font = `${size}px system-ui, -apple-system, Segoe UI, sans-serif`; const words = String(t).split(' '); let line = '';
    for (const wd of words) { const test = (line + ' ' + wd).trim(); if (c.measureText(test).width > w && line) { text(c, line, x, y, size, color); y += size * lh; line = wd; } else line = test; }
    if (line) text(c, line, x, y, size, color); return y + size * lh;
  }
  function rrect(c, x, y, w, h, r, fill, stroke, lw = 1) { c.beginPath(); c.roundRect(x, y, w, h, r); if (fill) { c.fillStyle = fill; c.fill(); } if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw; c.stroke(); } }
  function circle(c, x, y, r, fill, stroke, lw = 2) { c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); if (fill) { c.fillStyle = fill; c.fill(); } if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw; c.stroke(); } }
  const STARS = Array.from({length: 110}, (_, i) => { const r = seeded(i + 9); return [r() * 1280, r() * 720, r() < .7 ? 1 : 2]; });
  function space(c, W = 1280, H = 720) { c.fillStyle = COL.bg; c.fillRect(0, 0, W, H); c.fillStyle = '#c8cddc'; for (const [x, y, s] of STARS) { c.globalAlpha = .55; c.fillRect(x * W / 1280, y * H / 720, s, s); } c.globalAlpha = 1; }
  function satelliteIcon(c, x, y, r) { rrect(c, x - r * .45, y - r * .45, r * .9, r * .9, 4, '#c9d3e8', '#ffffff'); rrect(c, x - r * 1.5, y - r * .28, r * .9, r * .56, 2, '#2f5db8', '#8fb4ff'); rrect(c, x + r * .6, y - r * .28, r * .9, r * .56, 2, '#2f5db8', '#8fb4ff'); }
  function debrisIcon(c, x, y, r, seed) { const g = seeded(seed || 3); c.beginPath(); for (let k = 0; k < 9; k++) { const a = k / 9 * Math.PI * 2, rr = r * (0.6 + g() * 0.45); c.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); } c.closePath(); c.fillStyle = '#8a5a3c'; c.fill(); c.strokeStyle = '#ff9b6a'; c.lineWidth = 3; c.stroke(); }
  /* intro / message screen inside a stage: resolves on SPACE / ENTER / click on the button */
  function card(s, draw, label = 'Start (SPACE)') {
    return new Promise(resolve => {
      let btn = null, live = true;
      const go = () => { if (!live) return; live = false; s.on('key', null); s.on('down', null); resolve(); };
      s.on('key', code => { if (code === 'Space' || code === 'Enter') go(); });
      s.on('down', p => { if (btn && p.x >= btn[0] && p.x <= btn[0] + btn[2] && p.y >= btn[1] && p.y <= btn[1] + btn[3]) go(); });
      const step = () => {
        if (!live || s.done) return;
        const c = s.begin(), W = s.mode === 'fixed' ? 1280 : s.W, H = s.mode === 'fixed' ? 720 : s.H;
        space(c, W, H); draw(c, W, H);
        c.font = '700 22px system-ui'; const tw = c.measureText(label).width + 50; btn = [W / 2 - tw / 2, H - 110, tw, 54];
        rrect(c, ...btn, 12, COL.accent); text(c, label, W / 2, H - 83, 22, '#031018', {bold: true});
        requestAnimationFrame(step);
      };
      step();
    });
  }
  const wait = ms => new Promise(r => setTimeout(r, ms));

  /* =================================================================
     GAME 1  ORBIT OPS  (reaction time) - config.py / core/*.py
     ================================================================= */
  const OC = {
    TASK_VERSION: 'orbitops-web-1.0', FALSE_START_MS: 100,
    R1_TRIALS: 30, R1_ISI_S: [1.0, 4.0], R1_TIMEOUT_S: 2.0, R1_LAPSE_MS: 355, R1_FEEDBACK_S: 0.6,
    R2_TRIALS: 25, R2_GO_TRIALS: 18, R2_ISI_S: [0.8, 1.6], R2_WINDOW_S: 1.0, R2_FEEDBACK_S: 0.5,
    R3_TRIALS: 24, R3_BLOCK_LEN: [3, 5], R3_ISI_S: [0.5, 0.9], R3_WINDOW_S: 2.5, R3_NEW_ORDERS_S: 1.3, R3_FEEDBACK_S: 0.45, R3_CONGRUENT_SHARE: 1 / 3,
    R3_SHAPE_MAP: {triangle: 'left', circle: 'right'}, R3_COLOR_MAP: {orange: 'left', blue: 'right'}, BREATHER_S: 5.0,
    FAMILIARISATION_SESSIONS: 3, BASELINE_MIN_SESSIONS: 3, BASELINE_MAX_SESSIONS: 10, HIGH_CONFIDENCE_SESSIONS: 5,
    Z_SLOWER: 2.0, Z_SWITCH_COST: 2.5,
    SPREAD_FLOORS: {r1_median_ms: 15, r1_lapses: 1.0, decision_time_ms: 25, r2_false_alarms: 1.0, switch_cost_ms: 40, r3_accuracy: 0.05},
    GENERIC: {r1_median_ms: 380, r1_lapses: 5, r2_false_alarms: 3, r2_accuracy: 0.80, r3_accuracy: 0.75},
    SHORT_SLEEP_H: 6.0, HIGH_FATIGUE: 5, MAX_FALSE_STARTS: 5, MIN_VALID_R1: 15, MAX_R3_TIMEOUTS: 8,
  };
  function orbitSchedule(q) {
    const n1 = q ? 10 : OC.R1_TRIALS, n2 = q ? 10 : OC.R2_TRIALS, ngo = q ? 7 : OC.R2_GO_TRIALS, n3 = q ? 12 : OC.R3_TRIALS;
    const r1 = Array.from({length: n1}, (_, i) => ({round: 1, trial: i + 1, condition: 'alarm', isi_s: rnd(...OC.R1_ISI_S)}));
    let kinds;
    for (;;) { kinds = shuffle([...Array(ngo).fill('debris'), ...Array(n2 - ngo).fill('satellite')]); let run = 0, ok = true; for (const k of kinds) { run = k === 'satellite' ? run + 1 : 0; if (run > 3) { ok = false; break; } } if (ok) break; }
    const r2 = kinds.map((k, i) => ({round: 2, trial: i + 1, condition: k === 'debris' ? 'go' : 'no_go', stimulus: k, isi_s: rnd(...OC.R2_ISI_S), seed: rint(1, 1e6)}));
    const rules = []; let rule = choice(['shape', 'color']);
    while (rules.length < n3) { for (let k = rint(...OC.R3_BLOCK_LEN); k > 0 && rules.length < n3; k--) rules.push(rule); rule = rule === 'shape' ? 'color' : 'shape'; }
    const r3 = rules.map((rule, i) => {
      const congruent = Math.random() < OC.R3_CONGRUENT_SHARE, shape = choice(Object.keys(OC.R3_SHAPE_MAP));
      const colors = Object.keys(OC.R3_COLOR_MAP).filter(c => (OC.R3_COLOR_MAP[c] === OC.R3_SHAPE_MAP[shape]) === congruent), color = choice(colors);
      return {round: 3, trial: i + 1, rule, is_switch: +(i > 0 && rule !== rules[i - 1]), is_first: +(i === 0), condition: i > 0 && rule !== rules[i - 1] ? 'switch' : (i === 0 ? 'first' : 'repeat'),
        congruent: +congruent, shape, color, stimulus: `${color}_${shape}`, correct_key: rule === 'shape' ? OC.R3_SHAPE_MAP[shape] : OC.R3_COLOR_MAP[color], isi_s: rnd(...OC.R3_ISI_S)};
    });
    return [r1, r2, r3];
  }
  function orbitScore(t1, t2, t3) {
    const hits = t1.filter(t => t.response === 'hit'), rts = hits.map(t => t.rt_ms);
    let tot = null; if (hits.length >= 9) { const th = Math.floor(hits.length / 3); tot = median(hits.slice(-th).map(t => t.rt_ms)) - median(hits.slice(0, th).map(t => t.rt_ms)); }
    const tail = (v, f, slow) => { if (!v.length) return null; const s = [...v].sort((a, b) => slow ? b - a : a - b); return mean(s.slice(0, Math.max(1, Math.round(s.length * f)))); };
    const o = {r1_valid: rts.length, r1_median_ms: R(median(rts)), r1_mean_ms: R(mean(rts)), r1_sd_ms: R(sd(rts)), r1_speed: R(mean(rts.map(r => 1000 / r)), 3),
      r1_fast10_ms: R(tail(rts, .1, false)), r1_slow10_ms: R(tail(rts, .1, true)),
      r1_lapses: rts.filter(r => r >= OC.R1_LAPSE_MS).length + t1.filter(t => t.response === 'miss').length,
      r1_misses: t1.filter(t => t.response === 'miss').length, r1_false_starts: t1.filter(t => t.response === 'false_start').length, r1_time_on_task_ms: R(tot)};
    const go = t2.filter(t => t.condition === 'go'), nogo = t2.filter(t => t.condition === 'no_go'), h2 = go.filter(t => t.response === 'hit');
    const crs = nogo.filter(t => t.response === 'correct_rejection').length;
    Object.assign(o, {r2_go_rt_ms: R(median(h2.map(t => t.rt_ms))), r2_hits: h2.length, r2_misses: go.filter(t => t.response === 'miss').length,
      r2_false_alarms: nogo.filter(t => t.response === 'false_alarm').length, r2_correct_holds: crs, r2_false_starts: t2.filter(t => t.response === 'false_start').length,
      r2_accuracy: R((h2.length + crs) / (t2.length || 1), 3)});
    const ok = t3.filter(t => t.correct), sw = median(ok.filter(t => t.condition === 'switch').map(t => t.rt_ms)), rep = median(ok.filter(t => t.condition === 'repeat').map(t => t.rt_ms));
    const nsw = t3.filter(t => t.condition === 'switch').length, timeouts = t3.filter(t => t.response === 'miss').length;
    Object.assign(o, {r3_switch_rt_ms: R(sw), r3_repeat_rt_ms: R(rep), switch_cost_ms: sw != null && rep != null ? R(sw - rep) : null, r3_accuracy: R(ok.length / (t3.length || 1), 3),
      r3_switch_accuracy: nsw ? R(t3.filter(t => t.condition === 'switch' && t.correct).length / nsw, 3) : null,
      r3_old_rule_errors: t3.filter(t => t.response === 'old_rule').length, r3_errors: t3.length - ok.length - timeouts, r3_timeouts: timeouts});
    o.decision_time_ms = o.r2_go_rt_ms != null && o.r1_median_ms != null ? o.r2_go_rt_ms - o.r1_median_ms : null;
    o.reaction_ms = o.r1_median_ms;
    return o;
  }
  function robustBase(history, keysFloors, famil, minN, maxN) {
    const use = history.filter(h => !h.invalid && (num(h.session_index) || 0) > famil && h.data_source !== 'practice').slice(-maxN);
    if (use.length < minN) return null;
    const b = {n: use.length, n_simulated: use.filter(h => h.data_source === 'simulated').length};
    for (const [key, floor] of keysFloors) { const v = use.map(h => num(h[key])).filter(x => x != null); if (v.length < minN) continue; const c = median(v); b[key] = {centre: c, spread: Math.max(1.4826 * median(v.map(x => Math.abs(x - c))), floor)}; }
    return b;
  }
  function context(checkin) {
    const sleep = num(checkin.sleep_hours), fat = num(checkin.fatigue), stress = num(checkin.stress), ctx = [];
    if (sleep != null && sleep < 6) ctx.push(`short sleep (${sleep} h)`); if (fat != null && fat >= 5) ctx.push(`high fatigue (${fat}/7)`);
    const tired = ctx.length > 0; if (stress != null && stress >= 4) ctx.push(`high stress (${stress}/5)`); return {ctx, tired};
  }
  function confidence(invalid, base, idx, famil) {
    let conf, why;
    if (invalid) [conf, why] = ['LOW', 'data-quality problems'];
    else if (base && base.n >= 5) [conf, why] = ['HIGH', `personal baseline from ${base.n} sessions`];
    else if (base) [conf, why] = ['MEDIUM', `personal baseline still forming (${base.n} sessions)`];
    else if (idx <= famil) [conf, why] = ['LOW', `familiarisation session ${idx}/${famil}`];
    else [conf, why] = ['LOW', 'not enough valid sessions yet - generic reference used'];
    return {conf, why};
  }
  function orbitEvaluate(s, checkin, history, idx, q) {
    const base = robustBase(history, Object.entries(OC.SPREAD_FLOORS), OC.FAMILIARISATION_SESSIONS, OC.BASELINE_MIN_SESSIONS, OC.BASELINE_MAX_SESSIONS);
    const k = q ? 1 / 3 : 1, quality = [];
    if ((s.r1_false_starts || 0) > Math.max(2, Math.round(OC.MAX_FALSE_STARTS * k))) quality.push(`${s.r1_false_starts} false starts in Round 1 (pressing before the alarm)`);
    if ((s.r1_valid || 0) < Math.round(OC.MIN_VALID_R1 * k)) quality.push(`only ${s.r1_valid || 0} valid alarm responses in Round 1`);
    if ((s.r3_timeouts || 0) > Math.max(2, Math.round(OC.MAX_R3_TIMEOUTS * k))) quality.push(`${s.r3_timeouts} timeouts in Round 3`);
    const invalid = quality.length > 0, comp = {alertness: [], decision: [], adaptation: []};
    const z = (key, v) => base && base[key] && v != null ? (v - base[key].centre) / base[key].spread : null;
    if (base) {
      if (z('r1_median_ms', s.r1_median_ms) > OC.Z_SLOWER) comp.alertness.push(`reaction ${s.r1_median_ms} ms vs your normal ~${Math.round(base.r1_median_ms.centre)} ms`);
      if (base.r1_lapses && s.r1_lapses > base.r1_lapses.centre + 2) comp.alertness.push(`${s.r1_lapses} lapses vs your usual ~${Math.round(base.r1_lapses.centre)}`);
      if (z('decision_time_ms', s.decision_time_ms) > OC.Z_SLOWER) comp.decision.push(`decision time ${s.decision_time_ms} ms vs your normal ~${Math.round(base.decision_time_ms.centre)} ms`);
      if (base.r2_false_alarms && s.r2_false_alarms > base.r2_false_alarms.centre + 2) comp.decision.push(`${s.r2_false_alarms} shots at friendly satellites`);
      if (z('switch_cost_ms', s.switch_cost_ms) > OC.Z_SWITCH_COST) comp.adaptation.push(`switch cost +${s.switch_cost_ms} ms vs your normal ~${Math.round(base.switch_cost_ms.centre)} ms`);
      if (z('r3_accuracy', s.r3_accuracy) < -OC.Z_SLOWER) comp.adaptation.push(`order accuracy ${Math.round(s.r3_accuracy * 100)}%`);
    } else {
      const g = OC.GENERIC;
      if (s.r1_median_ms != null && s.r1_median_ms > g.r1_median_ms) comp.alertness.push(`reaction ${s.r1_median_ms} ms is above the generic ${g.r1_median_ms} ms`);
      if ((s.r1_lapses || 0) >= g.r1_lapses) comp.alertness.push(`${s.r1_lapses} lapses`);
      if ((s.r2_false_alarms || 0) >= g.r2_false_alarms || (s.r2_accuracy != null && s.r2_accuracy < g.r2_accuracy)) comp.decision.push(`debris accuracy ${Math.round(s.r2_accuracy * 100)}%, ${s.r2_false_alarms} friendly-fire shots`);
      if (s.r3_accuracy != null && s.r3_accuracy < g.r3_accuracy) comp.adaptation.push(`order accuracy ${Math.round(s.r3_accuracy * 100)}%`);
    }
    const slower = Object.keys(comp).filter(c => comp[c].length), {ctx, tired} = context(checkin);
    let status, headline, message;
    if (invalid) [status, headline, message] = ['RETEST', 'Session not reliable: please retest', quality.join('; ')];
    else if (slower.length && tired) [status, headline, message] = ['NO-GO', 'Avoid safety-critical tasks today', `Your ${slower.join(' and ')} slowed down AND you reported ${ctx.filter(c => !c.startsWith('high stress')).join(' and ')}.`];
    else if (slower.length) [status, headline, message] = ['CAUTION', 'Below your normal: retest in 2-4 h', `Your ${slower.join(' and ')} slowed down without a sleep/fatigue explanation.`];
    else if (tired) [status, headline, message] = ['CAUTION', "Scores OK, but you're running on low sleep", 'Fatigue often catches up later in the day. Retest before critical tasks.'];
    else [status, headline, message] = ['GO', 'Within your normal range', base ? 'Alertness, decision and adaptation all look like your usual performance.' : 'No concerns against the generic reference. Your personal baseline is still forming.'];
    return {status, headline, message, reasons: Object.values(comp).flat(), invalid, ...confidence(invalid, base, idx, OC.FAMILIARISATION_SESSIONS)};
  }
  async function playOrbit(opts) {
    const q = opts.quick, s = stage('GAME 1 · ORBIT OPS · reaction time');
    const [T1, T2, T3] = orbitSchedule(q), total = T1.length + T2.length + T3.length;
    const res = {1: [], 2: [], 3: []};
    let doneN = 0;
    const loop = s.loop(() => {});        // keeps the overlay alive; rounds drive their own frames
    const runRound = (n, trials) => new Promise(resolve => {
      let i = 0, state = 'start', end = 0, onset = null, onsetPending = false, fb = null, repeats = 0, streak = 0, laserUntil = 0, flash = {left: 0, right: 0};
      const T = () => trials[i], now = () => performance.now();
      const window_ = {1: OC.R1_TIMEOUT_S, 2: OC.R2_WINDOW_S, 3: OC.R3_WINDOW_S}[n] * 1000, isiR = {1: OC.R1_ISI_S, 2: OC.R2_ISI_S, 3: OC.R3_ISI_S}[n];
      const record = (response, correct, rt, key = '', counts = true) => { const t = T(); res[n].push({round: n, trial: t.trial, condition: t.condition, rule: t.rule, is_switch: t.is_switch, congruent: t.congruent, stimulus: t.stimulus, response, correct: +!!correct, rt_ms: rt, key}); if (counts) doneN++; };
      const feedback = (text_, color, sub, dur, then = 'next') => { fb = {text_, color, sub, then}; state = 'feedback'; end = now() + dur * 1000; };
      const begin = () => { fb = null; const t = T(); if (n === 3 && (t.is_first || t.is_switch)) { state = 'banner'; end = now() + (t.is_first ? 2000 : OC.R3_NEW_ORDERS_S * 1000); } else { state = 'isi'; end = now() + t.isi_s * 1000; } };
      const restart = () => { fb = null; state = 'isi'; end = now() + T().isi_s * 1000; };
      begin();
      s.on('key', (code, ts) => {
        const rtOf = () => ts - onset;
        if (n === 1 || n === 2) {
          if (code !== 'Space') return;
          press(rtOf, 'space');
        } else {
          const side = code === 'KeyF' ? 'left' : code === 'KeyJ' ? 'right' : null; if (!side) return; flash[side] = now() + 180; press(rtOf, side);
        }
      });
      s.on('down', (p, ts) => { const rtOf = () => ts - onset; if (n === 3) { const side = p.x < 640 ? 'left' : 'right'; flash[side] = now() + 180; press(rtOf, side); } else press(rtOf, 'click'); });
      function press(rtOf, key) {
        if (state === 'isi') { record('false_start', false, null, key, false); streak = 0; feedback(n === 1 ? 'TOO EARLY' : n === 2 ? 'WAIT FOR CONTACT' : 'WAIT FOR THE TARGET', COL.red, n === 1 ? 'wait for the alarm' : '', 0.7, 'repeat'); return; }
        if (state !== 'stim' || onset == null) return;
        const rt = rtOf();
        if (rt < OC.FALSE_START_MS) { record('false_start', false, rt, key); streak = 0; feedback('TOO EARLY', COL.red, n === 1 ? 'anticipation' : '', 0.7); return; }
        if (n === 1) { const lapse = rt >= OC.R1_LAPSE_MS; record('hit', true, rt, key); streak = lapse ? 0 : streak + 1; feedback(`${Math.round(rt)} ms`, lapse ? COL.amber : COL.green, lapse ? 'LAPSE' : '', OC.R1_FEEDBACK_S); }
        else if (n === 2) { laserUntil = now() + 150; if (T().stimulus === 'debris') { record('hit', true, rt, key); feedback('DEBRIS CLEARED', COL.green, `${Math.round(rt)} ms`, OC.R2_FEEDBACK_S); } else { record('false_alarm', false, rt, key); feedback('FRIENDLY FIRE!', COL.red, 'that was a satellite: hold fire', 0.8); } }
        else { const t = T(); if (key === t.correct_key) { record('correct', true, rt, key); feedback('CORRECT', COL.green, `${Math.round(rt)} ms`, OC.R3_FEEDBACK_S); } else { record(t.congruent ? 'wrong' : 'old_rule', false, rt, key); feedback('WRONG THRUSTER', COL.red, `orders are ${t.rule.toUpperCase()}`, 0.8); } }
      }
      const frame = () => {
        if (s.done) return resolve(null);
        const t = now();
        if (state === 'isi' && t >= end) { state = 'stim'; onset = null; onsetPending = true; }
        else if (state === 'stim' && onset != null && t - onset >= window_) {
          if (n === 1) { record('miss', false, null); streak = 0; feedback('MISSED', COL.red, '', 0.8); }
          else if (n === 2) { if (T().stimulus === 'debris') { record('miss', false, null); feedback('DEBRIS MISSED', COL.red, '', 0.7); } else { record('correct_rejection', true, null); feedback('SATELLITE SAFE', COL.green, 'good hold', OC.R2_FEEDBACK_S); } }
          else { record('miss', false, null); feedback('TOO SLOW', COL.red, '', 0.7); }
        } else if (state === 'feedback' && t >= end) {
          if (fb.then === 'repeat' && repeats < 3) { repeats++; T().isi_s = rnd(...isiR); restart(); }
          else { repeats = 0; i++; if (i >= trials.length) { s.on('key', null); s.on('down', null); return resolve(true); } begin(); }
        } else if (state === 'banner' && t >= end) { state = 'isi'; end = t + T().isi_s * 1000; }
        draw(t);
        if (onsetPending && state === 'stim') { onset = performance.now(); onsetPending = false; }   // stimulus is on this frame
        s.status(`ROUND ${n} · TRIAL ${Math.min(i + 1, trials.length)}/${trials.length}`); s.progress(doneN / total);
        requestAnimationFrame(frame);
      };
      function draw(t) {
        const c = s.begin(); space(c);
        const tr = T();
        if (n === 1) {
          rrect(c, 260, 120, 760, 470, 24, '#0a101e', COL.line);
          const on = state === 'stim';
          if (on) { const g = c.createRadialGradient(640, 360, 20, 640, 360, 200); g.addColorStop(0, 'rgba(255,60,60,.55)'); g.addColorStop(1, 'rgba(255,60,60,0)'); c.fillStyle = g; c.fillRect(440, 160, 400, 400); }
          circle(c, 640, 360, 120, on ? '#ff3b3b' : '#3a1418', on ? '#ffd0d0' : '#5a2a30', 4);
          if (on && onset != null) text(c, String(Math.round(t - onset)).padStart(3, '0'), 640, 360, 56, '#3c0a0a', {bold: true, mono: true});
          else if (state === 'feedback' && fb) { text(c, fb.text_, 640, 354, 44, fb.color, {bold: true, mono: true}); if (fb.sub) text(c, fb.sub.toUpperCase(), 640, 400, 18, fb.color, {bold: true, mono: true}); }
          text(c, 'STEADY STREAK', 640, 560, 15, COL.muted, {mono: true});
          for (let k = 0; k < 10; k++) rrect(c, 490 + k * 30, 576, 24, 8, 3, k < Math.min(streak, 10) ? COL.green : COL.line);
          text(c, 'Press SPACE (or click) the instant the MASTER ALARM lights up. Don’t guess.', 640, 680, 18, COL.muted);
        } else if (n === 2) {
          for (const r of [230, 160, 90]) circle(c, 640, 380, r, null, '#1f3a4a', 2);
          c.strokeStyle = '#1f3a4a'; c.beginPath(); c.moveTo(410, 380); c.lineTo(870, 380); c.moveTo(640, 150); c.lineTo(640, 610); c.stroke();
          const show = state === 'stim' || (state === 'feedback' && tr.stimulus === 'satellite' && fb && fb.text_ !== 'TOO EARLY' && fb.text_ !== 'WAIT FOR CONTACT');
          if (show) tr.stimulus === 'debris' ? debrisIcon(c, 640, 380, 62, tr.seed) : satelliteIcon(c, 640, 380, 50);
          if (t < laserUntil) { c.strokeStyle = '#ff5a5a'; c.lineWidth = 6; c.beginPath(); c.moveTo(640, 660); c.lineTo(640, 380); c.stroke(); c.lineWidth = 1; }
          if (state === 'feedback' && fb) { text(c, fb.text_, 640, 120, 34, fb.color, {bold: true, mono: true}); if (fb.sub) text(c, fb.sub, 640, 152, 18, fb.color, {mono: true}); }
          rrect(c, 40, 250, 210, 260, 12, '#0a101e', COL.line); debrisIcon(c, 145, 320, 34, 7); text(c, 'DEBRIS = FIRE', 145, 372, 17, COL.red, {bold: true, mono: true});
          satelliteIcon(c, 145, 430, 26); text(c, 'SATELLITE = HOLD', 145, 480, 17, COL.green, {bold: true, mono: true});
          text(c, 'SPACE (or click) = fire at DEBRIS. Do NOT fire at friendly SATELLITES.', 640, 690, 18, COL.muted);
        } else {
          const banner = (rule, y, big) => {
            text(c, `ORDERS:  BY ${rule.toUpperCase()}`, 640, y, big ? 40 : 28, big ? COL.amber : COL.text, {bold: true});
            const y2 = y + (big ? 60 : 44);
            const L = rule === 'shape' ? ['TRIANGLE', 'CIRCLE'] : ['ORANGE', 'BLUE'];
            rrect(c, 450, y2 - 18, 36, 36, 6, COL.panel2, COL.line); text(c, 'F', 468, y2, 20, COL.text, {bold: true, mono: true});
            if (rule === 'shape') { c.fillStyle = '#fff'; c.beginPath(); c.moveTo(520, y2 - 16); c.lineTo(536, y2 + 12); c.lineTo(504, y2 + 12); c.closePath(); c.fill(); circle(c, 750, y2, 15, '#fff'); }
            else { rrect(c, 504, y2 - 16, 32, 32, 6, COL.orange); rrect(c, 734, y2 - 16, 32, 32, 6, COL.blue); }
            text(c, L[0], 548, y2, 18, COL.muted, {bold: true, mono: true, align: 'left'});
            rrect(c, 680, y2 - 18, 36, 36, 6, COL.panel2, COL.line); text(c, 'J', 698, y2, 20, COL.text, {bold: true, mono: true});
            text(c, L[1], 778, y2, 18, COL.muted, {bold: true, mono: true, align: 'left'});
          };
          if (state === 'banner') { rrect(c, 260, 200, 760, 300, 18, '#181208', COL.amber, 2); text(c, tr.is_first ? 'INITIAL ORDERS' : 'NEW ORDERS FROM MISSION CONTROL', 640, 245, 22, COL.amber, {bold: true, mono: true}); banner(tr.rule, 320, true); }
          else {
            rrect(c, 300, 70, 680, 110, 14, '#0c1222', COL.line); banner(tr.rule, 100, false);
            rrect(c, 420, 220, 440, 360, 18, '#090e1b', COL.line);
            if (state === 'stim') { const col = tr.color === 'orange' ? COL.orange : COL.blue; c.fillStyle = col; if (tr.shape === 'circle') circle(c, 640, 400, 60, col); else { c.beginPath(); c.moveTo(640, 330); c.lineTo(705, 452); c.lineTo(575, 452); c.closePath(); c.fill(); } }
            else if (state === 'feedback' && fb) { text(c, fb.text_, 640, 390, 36, fb.color, {bold: true, mono: true}); if (fb.sub) text(c, fb.sub, 640, 430, 18, fb.color, {mono: true}); }
            else text(c, '+', 640, 400, 40, COL.dim, {mono: true});
            for (const [side, x, k] of [['left', 250, 'F'], ['right', 1030, 'J']]) { const lit = t < flash[side]; rrect(c, x - 75, 345, 150, 110, 16, lit ? '#283c64' : '#0e1628', lit ? COL.accent : COL.line, 2); text(c, k, x, 385, 40, COL.text, {bold: true, mono: true}); text(c, `${side.toUpperCase()} THRUSTER`, x, 425, 13, COL.muted, {mono: true}); }
          }
          text(c, 'Follow the CURRENT orders:  F = left   J = right   (or click the left / right half)', 640, 690, 18, COL.muted);
        }
      }
      requestAnimationFrame(frame);
    });
    const BRIEF = {
      1: ['ROUND 1 · MASTER ALARM', 'The alarm lights up at a random moment. Press SPACE (or click) as fast as you can. Don’t press before it lights up.', 'Measures alertness (NASA PVT-B rules: lapses ≥ 355 ms).'],
      2: ['ROUND 2 · DEBRIS WATCH', 'DEBRIS = fire (SPACE / click). SATELLITE = hold fire. Be fast, but don’t shoot friendlies.', 'Measures decision speed and self-control (go / no-go).'],
      3: ['ROUND 3 · MISSION CONTROL ORDERS', 'Sort the object by SHAPE or COLOR, whichever the orders say. F = left thruster, J = right. The orders switch every few objects.', 'Measures adaptation: how much slower you are right after the rule switches.'],
    };
    for (const [n, trials] of [[1, T1], [2, T2], [3, T3]]) {
      await card(s, (c) => { text(c, BRIEF[n][0], 640, 200, 40, COL.accent, {bold: true}); wrapText(c, BRIEF[n][1], 640, 290, 820, 22, COL.text); text(c, BRIEF[n][2], 640, 420, 17, COL.muted); if (q) text(c, 'QUICK VERSION · fewer trials', 640, 140, 15, COL.gold, {bold: true, mono: true}); }, n === 1 ? 'Start (SPACE)' : 'Next round (SPACE)');
      if (s.done) return null;
      const ok = await runRound(n, trials);
      if (!ok || s.done) { s.finish && s.finish(null); return null; }
    }
    const scores = orbitScore(res[1], res[2], res[3]);
    const idx = opts.sessionIndex || opts.history.length + 1;
    const ev = orbitEvaluate(scores, opts.checkin, opts.history, idx, q);
    await card(s, (c) => resultScreen(c, 'ORBIT OPS · DEBRIEF', ev, [[`${scores.r1_median_ms ?? '—'} ms`, 'reaction (Round 1 median)'], [`${scores.decision_time_ms ?? '—'} ms`, 'decision time (R2 − R1)'], [`${scores.switch_cost_ms ?? '—'} ms`, 'switch cost (Round 3)']]), 'Save and close (SPACE)');
    s.finish(true); await loop;
    return {game: 'orbit', session_index: idx, scores, ev, fields: {reaction_ms: scores.reaction_ms}, result: `reaction ${scores.reaction_ms ?? '—'} ms`,
      used: !ev.invalid && idx > OC.FAMILIARISATION_SESSIONS, why: ev.invalid ? 'game asked for a retest' : idx <= OC.FAMILIARISATION_SESSIONS ? 'familiarisation session' : ''};
  }
  function resultScreen(c, title, ev, cards) {
    const col = {GO: COL.green, CAUTION: COL.amber, GLASSES: COL.amber, CHECK: COL.amber, 'NO-GO': COL.red, 'SCAN NOW': COL.red, RETEST: COL.muted}[ev.status] || COL.muted;
    text(c, title, 640, 70, 16, COL.muted, {bold: true, mono: true});
    rrect(c, 160, 100, 960, 210, 18, COL.panel2, col, 2); circle(c, 230, 170, 34, col);
    text(c, ev.status, 290, 150, 40, col, {bold: true, align: 'left'}); text(c, ev.headline, 290, 196, 22, COL.text, {bold: true, align: 'left'});
    c.textAlign = 'left'; wrapTextLeft(c, ev.message, 290, 232, 800, 16, COL.muted);
    text(c, `CONFIDENCE ${ev.conf} · ${ev.why}`, 290, 290, 14, COL.muted, {mono: true, align: 'left'});
    cards.forEach(([v, l], k) => { const x = 160 + k * 330; rrect(c, x, 340, 300, 130, 14, COL.panel, COL.line); text(c, v, x + 150, 392, 34, COL.accent, {bold: true, mono: true}); text(c, l, x + 150, 440, 15, COL.muted); });
    (ev.reasons || []).slice(0, 3).forEach((r, k) => text(c, '› ' + r, 640, 505 + k * 24, 16, COL.amber));
  }
  function wrapTextLeft(c, t, x, y, w, size, color) { c.font = `${size}px system-ui`; const words = String(t).split(' '); let line = ''; for (const wd of words) { const tt = (line + ' ' + wd).trim(); if (c.measureText(tt).width > w && line) { text(c, line, x, y, size, color, {align: 'left'}); y += size * 1.35; line = wd; } else line = tt; } if (line) text(c, line, x, y, size, color, {align: 'left'}); }

  /* =================================================================
     GAME 3  DOCKMASTER  (hand-eye + memory) - config.py / core/*.py
     ================================================================= */
  const DC = {TASK_VERSION: 'dockmaster-web-1.0', ARENA: [230, 110, 820, 540],
    T1_ROUNDS: 5, T1_PORTS: 5, T1_SHOW_S: 1.5, T1_PORT_RADIUS: 28, T1_MIN_GAP: 115, T1_ROUND_TIMEOUT_S: 10.0, T1_FEEDBACK_S: 0.9,
    T2_ROUNDS: 4, T2_SATELLITES: 6, T2_TAGGED: 2, T2_BLINK_S: 2.0, T2_MOVE_S: 6.0, T2_SPEED: 150, T2_RADIUS: 22, T2_ANSWER_TIMEOUT_S: 8.0, T2_FEEDBACK_S: 1.2,
    T3_ROUNDS: 2, T3_DURATION_S: 25.0, T3_ON_TARGET_PX: 30, T3_FLASHES: [7, 10], T3_GREEN: [3, 6], T3_FLASH_S: 0.4, T3_FLASH_GAP_S: 1.4, T3_ANSWER_MAX: 8, T3_ANSWER_TIMEOUT_S: 8.0,
    FAMILIARISATION_SESSIONS: 3, BASELINE_MIN_SESSIONS: 3, BASELINE_MAX_SESSIONS: 10, Z_FLAG: 2.0,
    METRICS: [['t1_order_acc', -1, 0.05, 0.80, 'memory', 'port order accuracy'], ['t2_accuracy', -1, 0.08, 0.70, 'memory', 'satellite tracking accuracy'],
      ['t1_click_err_px', 1, 2, 14, 'hand_eye', 'click error on ports (px)'], ['t1_click_time_ms', 1, 60, 1200, 'hand_eye', 'time between port clicks (ms)'],
      ['t3_track_err_px', 1, 3, 40, 'hand_eye', 'laser tracking error (px)'], ['t3_on_target_pct', -1, 4, 60, 'hand_eye', 'laser time on target (%)'],
      ['t3_count_err', 1, 1, 2, 'attention', 'green-flash counting error'], ['t2_select_time_ms', 1, 300, 4000, 'attention', 'time to pick tracked satellites (ms)']]};
  const arena = (pad = 40) => { const [x, y, w, h] = DC.ARENA; return [x + pad, y + pad, x + w - pad, y + h - pad]; };
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  function trackFrames(rnd_) {
    const [x0, y0, x1, y1] = arena(40), g = seeded(rnd_.seed), pos = rnd_.start.map(p => [...p]), head = [...rnd_.heading], turn = [...rnd_.turn], dt = 1 / 60, frames = [pos.map(p => [...p])];
    for (let k = 0; k < Math.round(DC.T2_MOVE_S * 60); k++) {
      for (let j = 0; j < pos.length; j++) {
        if (k % 60 === 0) turn[j] = Math.max(-1.5, Math.min(1.5, turn[j] + (g() * 1.2 - 0.6)));
        head[j] += turn[j] * dt; pos[j][0] += Math.cos(head[j]) * DC.T2_SPEED * dt; pos[j][1] += Math.sin(head[j]) * DC.T2_SPEED * dt;
        if (pos[j][0] < x0 || pos[j][0] > x1) { head[j] = Math.PI - head[j]; pos[j][0] = Math.min(Math.max(pos[j][0], x0), x1); }
        if (pos[j][1] < y0 || pos[j][1] > y1) { head[j] = -head[j]; pos[j][1] = Math.min(Math.max(pos[j][1], y0), y1); }
      }
      frames.push(pos.map(p => [...p]));
    }
    return frames;
  }
  function beamPos(r, t) { const [x, y, w, h] = DC.ARENA, [[fx1, px1], [fx2, px2], [fy1, py1], [fy2, py2]] = r.path, cx = x + w / 2, cy = y + h / 2, ax = w / 2 - 90, ay = h / 2 - 80, TAU = Math.PI * 2;
    return [cx + ax * (0.65 * Math.sin(TAU * fx1 * t + px1) + 0.35 * Math.sin(TAU * fx2 * t + px2)), cy + ay * (0.65 * Math.sin(TAU * fy1 * t + py1) + 0.35 * Math.sin(TAU * fy2 * t + py2))]; }
  function dockGen(q) {
    const nPorts = q ? 2 : DC.T1_ROUNDS, nTrack = q ? 2 : DC.T2_ROUNDS, nBeam = 1, dur = q ? 15 : DC.T3_DURATION_S, TAU = Math.PI * 2;
    const ports = Array.from({length: nPorts}, (_, i) => { const [x0, y0, x1, y1] = arena(50), pts = []; while (pts.length < DC.T1_PORTS) { const p = [rnd(x0, x1), rnd(y0, y1)]; if (pts.every(q2 => dist(p, q2) >= DC.T1_MIN_GAP)) pts.push(p); } return {round: i + 1, ports: pts}; });
    const track = Array.from({length: nTrack}, (_, i) => { const [x0, y0, x1, y1] = arena(40), sats = []; while (sats.length < DC.T2_SATELLITES) { const p = [rnd(x0, x1), rnd(y0, y1)]; if (sats.every(s2 => dist(p, s2) > 90)) sats.push(p); }
      return {round: i + 1, start: sats, heading: sats.map(() => rnd(0, TAU)), turn: sats.map(() => rnd(-1.2, 1.2)), tagged: shuffle([...Array(DC.T2_SATELLITES).keys()]).slice(0, DC.T2_TAGGED).sort(), seed: rint(1, 1e6)}; });
    const beam = Array.from({length: q ? nBeam : DC.T3_ROUNDS}, (_, i) => {
      const path = [[rnd(.08, .14), rnd(0, TAU)], [rnd(.18, .26), rnd(0, TAU)], [rnd(.07, .12), rnd(0, TAU)], [rnd(.15, .22), rnd(0, TAU)]];
      const total = q ? rint(4, 6) : rint(...DC.T3_FLASHES), greens = Math.min(q ? rint(2, 4) : rint(...DC.T3_GREEN), total);
      const colors = shuffle([...Array(greens).fill('green'), ...Array(total - greens).fill('red')]);
      const span = dur - 2.5; let times = Array.from({length: total}, () => rnd(1.5, 1.5 + span)).sort((a, b) => a - b);
      for (let k = 1; k < times.length; k++) times[k] = Math.max(times[k], times[k - 1] + DC.T3_FLASH_GAP_S);
      times = times.filter(t => t < dur - 0.8); const cols = colors.slice(0, times.length);
      const [x, y, w, h] = DC.ARENA;
      const edges = times.map(() => { const s2 = choice(['top', 'bottom', 'left', 'right']); return s2 === 'top' ? [rnd(x + 40, x + w - 40), y + 14] : s2 === 'bottom' ? [rnd(x + 40, x + w - 40), y + h - 14] : s2 === 'left' ? [x + 14, rnd(y + 40, y + h - 40)] : [x + w - 14, rnd(y + 40, y + h - 40)]; });
      return {round: i + 1, path, flashes: times.map((t, k) => [t, cols[k], edges[k]]), greens: cols.filter(c => c === 'green').length, dur};
    });
    return {ports, track, beam};
  }
  function dockScore(e1, e2, e3) {
    const clicks = e1.filter(e => e.kind === 'click'), rounds1 = e1.filter(e => e.kind === 'round'), onPort = clicks.filter(e => e.clicked);
    const picks = e2.filter(e => e.kind === 'pick'), rounds2 = e2.filter(e => e.kind === 'round'), b = e3.filter(e => e.kind === 'beam');
    return {t1_order_acc: clicks.length ? R(clicks.filter(e => e.correct).length / clicks.length, 3) : null, t1_perfect_rounds: rounds1.filter(r => r.perfect).length, t1_rounds: rounds1.length,
      t1_timeouts: rounds1.filter(r => r.timeout).length, t1_first_click_ms: R(median(rounds1.map(r => r.first_click_ms))), t1_click_time_ms: R(median(clicks.filter(e => !e.first).map(e => e.dt_ms))),
      t1_click_err_px: R(median(onPort.map(e => e.err_px)), 1), t1_empty_clicks: clicks.filter(e => !e.clicked).length,
      t2_correct: picks.filter(p => p.correct).length, t2_accuracy: rounds2.length ? R(picks.filter(p => p.correct).length / (rounds2.length * DC.T2_TAGGED), 3) : null,
      t2_perfect_rounds: rounds2.filter(r => r.n_correct === DC.T2_TAGGED).length, t2_rounds: rounds2.length, t2_select_time_ms: R(median(picks.map(p => p.time_ms))), t2_click_err_px: R(median(picks.map(p => p.err_px)), 1),
      t2_timeouts: rounds2.filter(r => r.timeout).length,
      t3_track_err_px: R(mean(b.map(e => e.track_err_px)), 1), t3_on_target_pct: R(mean(b.map(e => e.on_target_pct)), 1), t3_count_err: b.length ? b.reduce((a, e) => a + e.count_err, 0) : null,
      t3_count_correct: b.filter(e => e.count_err === 0).length, t3_rounds: b.length, t3_answer_ms: R(median(b.map(e => e.answer_ms)))};
  }
  function dockEvaluate(s, checkin, history, idx) {
    const base = robustBase(history, DC.METRICS.map(m => [m[0], m[2]]), DC.FAMILIARISATION_SESSIONS, DC.BASELINE_MIN_SESSIONS, DC.BASELINE_MAX_SESSIONS);
    const quality = []; if ((s.t1_timeouts || 0) >= 3) quality.push(`${s.t1_timeouts} port rounds timed out`); if (s.t3_on_target_pct != null && s.t3_on_target_pct < 10) quality.push('laser almost never on target (not tracking)');
    const invalid = quality.length > 0, comp = {hand_eye: [], memory: [], attention: []}, NAMES = {hand_eye: 'Hand-eye', memory: 'Memory', attention: 'Attention'};
    const f = x => Math.abs(x) >= 10 ? Math.round(x) : Math.round(x * 100) / 100;
    for (const [key, dir, , generic, component, label] of DC.METRICS) {
      const v = num(s[key]); if (v == null) continue;
      if (base && base[key]) { const z = (v - base[key].centre) / base[key].spread * dir; if (z > DC.Z_FLAG) comp[component].push(`${label}: ${f(v)} vs your normal ~${f(base[key].centre)}`); }
      else if (dir > 0 ? v > generic : v < generic) comp[component].push(`${label}: ${f(v)} (generic limit ${f(generic)})`);
    }
    const slower = Object.keys(comp).filter(c => comp[c].length), {ctx, tired} = context(checkin);
    let status, headline, message;
    if (invalid) [status, headline, message] = ['RETEST', 'Session not reliable: please retest', quality.join('; ')];
    else if (slower.length && tired) [status, headline, message] = ['NO-GO', 'Avoid safety-critical manual tasks today', `${slower.map(x => NAMES[x]).join(', ')} below your normal AND ${ctx.filter(c => !c.includes('stress')).join(' and ')}.`];
    else if (slower.length) [status, headline, message] = ['CAUTION', 'Below your normal: retest in 2-4 h', `${slower.map(x => NAMES[x]).join(', ')} below your normal without a sleep/fatigue explanation.`];
    else if (tired) [status, headline, message] = ['CAUTION', 'Scores nominal, but running on low sleep', 'Fatigue often catches up later. Retest before critical tasks.'];
    else [status, headline, message] = ['GO', 'All components nominal', base ? 'Hand-eye, memory and attention are within your normal range.' : 'No concerns against generic limits. Personal baseline still forming.'];
    return {status, headline, message, reasons: Object.values(comp).flat(), invalid, ...confidence(invalid, base, idx, DC.FAMILIARISATION_SESSIONS)};
  }
  async function playDock(opts) {
    const q = opts.quick, s = stage('GAME 3 · DOCKMASTER · hand-eye + memory'), G = dockGen(q);
    const ev1 = [], ev2 = [], ev3 = [], totalRounds = G.ports.length + G.track.length + G.beam.length; let roundsDone = 0;
    const loop = s.loop(() => {});
    const arenaBg = (c, grid = true) => { const [x, y, w, h] = DC.ARENA; rrect(c, x, y, w, h, 16, '#08101f', COL.line); if (grid) { c.strokeStyle = '#0f1b30'; c.lineWidth = 1; for (let gx = x + 40; gx < x + w; gx += 40) { c.beginPath(); c.moveTo(gx, y); c.lineTo(gx, y + h); c.stroke(); } for (let gy = y + 40; gy < y + h; gy += 40) { c.beginPath(); c.moveTo(x, gy); c.lineTo(x + w, gy); c.stroke(); } } };
    const head = (c, t, rule, sub) => { text(c, t, 640, 40, 24, COL.text, {bold: true}); text(c, rule, 640, 82, 18, COL.amber, {bold: true}); if (sub) text(c, sub, 640, 706, 14, COL.muted, {mono: true}); };
    const runTask = (draw, update, click, rounds) => new Promise(resolve => {
      let i = 0; const st = {i}; s.on('down', (p, ts) => click(p, performance.now(), st)); s.on('key', null);
      const frame = () => { if (s.done) return resolve(false); const now = performance.now(); const r = update(now, st); if (r === 'done') { s.on('down', null); return resolve(true); } const c = s.begin(); space(c); draw(c, now, st); s.progress(roundsDone / totalRounds); requestAnimationFrame(frame); };
      requestAnimationFrame(frame);
    });
    // ---- task 1: PORT SEQUENCE
    await card(s, c => { text(c, 'TASK 1 · PORT SEQUENCE', 640, 200, 40, COL.accent, {bold: true}); wrapText(c, 'Numbers 1–5 show on the docking ports for 1.5 s, then hide. Click the ports in order 1 → 5 from memory.', 640, 300, 820, 22, COL.text); text(c, 'Measures memory and hand-eye (click speed and accuracy).', 640, 420, 17, COL.muted); });
    if (s.done) return null;
    {
      let ri = 0, state, ts, expected, used, lastT, firstMs, ok;
      const begin = now => { expected = 1; used = new Map(); lastT = null; firstMs = null; ok = true; state = 'show'; ts = now; };
      const endRound = (now, timeout) => { ev1.push({task: 1, kind: 'round', round: ri + 1, perfect: +(ok && !timeout), timeout: +timeout, first_click_ms: firstMs}); state = 'feedback'; ts = now; };
      begin(performance.now());
      const done = await runTask((c, now) => {
        head(c, 'TASK 1 · PORT SEQUENCE', 'Click the docking ports in order: 1 → 2 → 3 → 4 → 5', `ROUND ${ri + 1}/${G.ports.length} · mouse click`); arenaBg(c);
        G.ports[ri].ports.forEach((p, k) => { const n = k + 1, r = DC.T1_PORT_RADIUS;
          if (state === 'show') { circle(c, p[0], p[1], r, '#10223a', COL.accent, 3); text(c, String(n), p[0], p[1], 26, COL.text, {bold: true, mono: true}); }
          else if (state === 'recall') { const hover = dist([s.mouse.x, s.mouse.y], p) <= r * 1.5 && !used.has(k); circle(c, p[0], p[1], r, '#0c1628', hover ? COL.accent : '#7887aa', 3); if (used.has(k)) text(c, String(used.get(k)), p[0], p[1], 22, COL.accent, {bold: true, mono: true}); }
          else { const mine = used.get(k), col = mine === n ? COL.green : mine ? COL.red : COL.dim; circle(c, p[0], p[1], r, '#0c1628', col, 3); text(c, String(n), p[0], p[1], 22, col, {bold: true, mono: true}); } });
        const msg = state === 'show' ? `MEMORISE · ${Math.max(0, DC.T1_SHOW_S - (now - ts) / 1000).toFixed(1)} s` : state === 'recall' ? `CLICK PORT ${expected}` : ok ? 'SEQUENCE CORRECT' : 'SEQUENCE ERROR';
        text(c, msg, 640, 672, 20, state === 'feedback' ? (ok ? COL.green : COL.red) : COL.text, {bold: true, mono: true});
      }, now => {
        const age = (now - ts) / 1000;
        if (state === 'show' && age >= DC.T1_SHOW_S) { state = 'recall'; ts = now; lastT = now; }
        else if (state === 'recall' && age >= DC.T1_ROUND_TIMEOUT_S) endRound(now, true);
        else if (state === 'feedback' && age >= DC.T1_FEEDBACK_S) { roundsDone++; ri++; if (ri >= G.ports.length) return 'done'; begin(now); }
      }, (p, now) => {
        if (state !== 'recall') return; const ports = G.ports[ri].ports;
        const free = ports.map((pp, k) => [dist([p.x, p.y], pp), k]).filter(([, k]) => !used.has(k)).sort((a, b) => a[0] - b[0]);
        const [d, k] = free[0] || [1e9, null], first = expected === 1 && used.size === 0, dt = now - lastT; if (first) firstMs = dt;
        if (k == null || d > DC.T1_PORT_RADIUS * 1.5) { ev1.push({task: 1, kind: 'click', round: ri + 1, expected, clicked: 0, correct: 0, first: +first, dt_ms: dt, err_px: null}); ok = false; lastT = now; return; }
        const number = k + 1, correct = number === expected;
        ev1.push({task: 1, kind: 'click', round: ri + 1, expected, clicked: number, correct: +correct, first: +first, dt_ms: dt, err_px: d});
        used.set(k, expected); ok = ok && correct; expected++; lastT = now; if (expected > DC.T1_PORTS) endRound(now, false);
      });
      if (!done) { s.finish && s.finish(null); return null; }
    }
    // ---- task 2: TRACK THE SATELLITE
    await card(s, c => { text(c, 'TASK 2 · TRACK THE SATELLITE', 640, 200, 40, COL.accent, {bold: true}); wrapText(c, 'Two satellites blink amber. Then all six move and mix for 6 s. When they stop, click the two that blinked.', 640, 300, 820, 22, COL.text); text(c, 'Measures memory for moving objects and eye tracking.', 640, 420, 17, COL.muted); }, 'Next task (SPACE)');
    if (s.done) return null;
    {
      let ri = 0, state, ts, frames, pos, picks, lastT, nOk = 0;
      const begin = now => { frames = trackFrames(G.track[ri]); pos = frames[0]; picks = []; lastT = null; state = 'blink'; ts = now; };
      const endRound = (now, timeout) => { nOk = picks.filter(j => G.track[ri].tagged.includes(j)).length; ev2.push({task: 2, kind: 'round', round: ri + 1, n_correct: nOk, n_targets: DC.T2_TAGGED, timeout: +timeout}); state = 'feedback'; ts = now; };
      begin(performance.now());
      const done = await runTask((c, now) => {
        head(c, 'TASK 2 · TRACK THE SATELLITE', 'Follow the satellites that blink. Click them when they stop.', `ROUND ${ri + 1}/${G.track.length} · follow with your eyes · click to select`); arenaBg(c);
        const tagged = G.track[ri].tagged, age = (now - ts) / 1000;
        pos.forEach((p, j) => { satelliteIcon(c, p[0], p[1], DC.T2_RADIUS * .8);
          if (state === 'blink' && tagged.includes(j) && Math.floor(age * 4) % 2 === 0) circle(c, p[0], p[1], DC.T2_RADIUS + 14, null, COL.amber, 3);
          if (state === 'answer' && !picks.includes(j) && dist([s.mouse.x, s.mouse.y], p) <= DC.T2_RADIUS * 1.8) circle(c, p[0], p[1], DC.T2_RADIUS + 12, null, COL.accent, 2);
          if (picks.includes(j)) circle(c, p[0], p[1], DC.T2_RADIUS + 12, null, state === 'answer' ? COL.accent : tagged.includes(j) ? COL.green : COL.red, 3);
          if (state === 'feedback' && tagged.includes(j) && !picks.includes(j)) circle(c, p[0], p[1], DC.T2_RADIUS + 12, null, COL.amber, 2); });
        const msg = {blink: 'WATCH THE BLINKING SATELLITES', move: 'KEEP YOUR EYES ON THEM', answer: `CLICK THE ${DC.T2_TAGGED} SATELLITES · ${picks.length}/${DC.T2_TAGGED}`, feedback: `${nOk}/${DC.T2_TAGGED} CORRECT`}[state];
        text(c, msg, 640, 672, 20, state === 'feedback' ? (nOk === DC.T2_TAGGED ? COL.green : COL.amber) : COL.text, {bold: true, mono: true});
      }, now => {
        const age = (now - ts) / 1000;
        if (state === 'blink' && age >= DC.T2_BLINK_S) { state = 'move'; ts = now; }
        else if (state === 'move') { pos = frames[Math.min(frames.length - 1, Math.floor(age * 60))]; if (age >= DC.T2_MOVE_S) { pos = frames[frames.length - 1]; state = 'answer'; ts = now; lastT = now; } }
        else if (state === 'answer' && age >= DC.T2_ANSWER_TIMEOUT_S) endRound(now, true);
        else if (state === 'feedback' && age >= DC.T2_FEEDBACK_S) { roundsDone++; ri++; if (ri >= G.track.length) return 'done'; begin(now); }
      }, (p, now) => {
        if (state !== 'answer') return;
        const cand = pos.map((pp, j) => [dist([p.x, p.y], pp), j]).filter(([, j]) => !picks.includes(j)).sort((a, b) => a[0] - b[0]); const [d, j] = cand[0];
        if (d > DC.T2_RADIUS * 1.8) return;
        picks.push(j); ev2.push({task: 2, kind: 'pick', round: ri + 1, correct: +G.track[ri].tagged.includes(j), time_ms: now - lastT, err_px: d}); lastT = now;
        if (picks.length >= DC.T2_TAGGED) endRound(now, false);
      });
      if (!done) { s.finish && s.finish(null); return null; }
    }
    // ---- task 3: STEADY BEAM
    await card(s, c => { text(c, 'TASK 3 · STEADY BEAM', 640, 200, 40, COL.accent, {bold: true}); wrapText(c, 'Move the mouse to keep the laser on the drifting satellite. At the same time, count the GREEN flashes at the edges. Ignore red ones.', 640, 300, 820, 22, COL.text); text(c, 'Measures hand-eye tracking and attention while busy.', 640, 420, 17, COL.muted); }, 'Next task (SPACE)');
    if (s.done) return null;
    {
      let ri = 0, state, ts, errSum, onTime, tTotal, lastNow, answer, btns = [];
      const begin = now => { errSum = 0; onTime = 0; tTotal = 0; answer = null; btns = []; state = 'ready'; ts = now; lastNow = now; };
      const finishRound = (ans, now) => { const g = G.beam[ri].greens, err = ans == null ? g : Math.abs(ans - g); answer = ans; ev3.push({task: 3, kind: 'beam', round: ri + 1, track_err_px: errSum / Math.max(tTotal, 1e-6), on_target_pct: 100 * onTime / Math.max(tTotal, 1e-6), greens: g, answer: ans, count_err: err, answer_ms: now - ts}); state = 'feedback'; ts = now; };
      begin(performance.now());
      const done = await runTask((c, now) => {
        const B = G.beam[ri], [x, y, w, h] = DC.ARENA, age = (now - ts) / 1000;
        head(c, 'TASK 3 · STEADY BEAM', 'Keep the laser on the satellite AND count the GREEN flashes.', `ROUND ${ri + 1}/${G.beam.length} · mouse = laser`); arenaBg(c, false);
        if (state === 'ready' || state === 'track') {
          const t = state === 'track' ? age : 0, tg = beamPos(B, t); satelliteIcon(c, tg[0], tg[1], 18);
          for (const [ft, colr, p] of B.flashes) if (state === 'track' && ft <= t && t <= ft + DC.T3_FLASH_S) { const cc = colr === 'green' ? COL.green : COL.red; c.shadowColor = cc; c.shadowBlur = 24; circle(c, p[0], p[1], 10, cc); c.shadowBlur = 0; }
          if (state === 'track') { const m = [s.mouse.x, s.mouse.y], on = dist(m, tg) <= DC.T3_ON_TARGET_PX; c.strokeStyle = on ? '#ff5a5a' : '#5a3c46'; c.lineWidth = 2; c.beginPath(); c.moveTo(x + w / 2, y + h); c.lineTo(m[0], m[1]); c.stroke();
            circle(c, m[0], m[1], 18, null, on ? COL.green : COL.accent, 2); c.beginPath(); c.moveTo(m[0] - 26, m[1]); c.lineTo(m[0] + 26, m[1]); c.moveTo(m[0], m[1] - 26); c.lineTo(m[0], m[1] + 26); c.stroke();
            text(c, `ON TARGET ${Math.round(100 * onTime / Math.max(tTotal, 1e-6))}%   ·   ${Math.max(0, B.dur - t).toFixed(1)} s`, 640, 672, 18, on ? COL.green : COL.text, {bold: true, mono: true}); }
          else text(c, 'GET READY · laser on the satellite · count GREEN flashes', 640, 672, 18, COL.text, {bold: true, mono: true});
        } else if (state === 'answer') {
          text(c, 'How many GREEN flashes did you see?', 640, 360, 30, COL.text, {bold: true});
          btns.forEach(([r, k]) => { const hov = s.mouse.x >= r[0] && s.mouse.x <= r[0] + r[2] && s.mouse.y >= r[1] && s.mouse.y <= r[1] + r[3]; rrect(c, ...r, 10, hov ? '#22345c' : COL.panel2, hov ? COL.accent : COL.line, 2); text(c, String(k), r[0] + r[2] / 2, r[1] + r[3] / 2, 26, COL.text, {bold: true}); });
          text(c, `${Math.max(0, DC.T3_ANSWER_TIMEOUT_S - age).toFixed(1)} s`, 640, 520, 16, COL.amber, {mono: true});
        } else { const g = B.greens, ok = answer === g, e = ev3[ev3.length - 1]; text(c, `${ok ? 'CORRECT' : 'NOT QUITE'} · there were ${g} green flashes`, 640, 380, 26, ok ? COL.green : COL.amber, {bold: true}); text(c, `Laser on target ${Math.round(e.on_target_pct)}% of the time`, 640, 430, 20, COL.text); }
      }, now => {
        const B = G.beam[ri], age = (now - ts) / 1000, dt = (now - lastNow) / 1000; lastNow = now;
        if (state === 'ready' && age >= 1.5) { state = 'track'; ts = now; }
        else if (state === 'track') { const tg = beamPos(B, age), d = dist([s.mouse.x, s.mouse.y], tg); errSum += d * dt; tTotal += dt; if (d <= DC.T3_ON_TARGET_PX) onTime += dt;
          if (age >= B.dur) { const n = DC.T3_ANSWER_MAX + 1, w = 80, x0 = 640 - (n * w + (n - 1) * 10) / 2; btns = Array.from({length: n}, (_, k) => [[x0 + k * (w + 10), 420, w, 64], k]); state = 'answer'; ts = now; } }
        else if (state === 'answer' && age >= DC.T3_ANSWER_TIMEOUT_S) finishRound(null, now);
        else if (state === 'feedback' && age >= 1.6) { roundsDone++; ri++; if (ri >= G.beam.length) return 'done'; begin(now); }
      }, (p, now) => { if (state !== 'answer') return; for (const [r, k] of btns) if (p.x >= r[0] && p.x <= r[0] + r[2] && p.y >= r[1] && p.y <= r[1] + r[3]) return finishRound(k, now); });
      if (!done) { s.finish && s.finish(null); return null; }
    }
    const scores = dockScore(ev1, ev2, ev3), idx = opts.sessionIndex || opts.history.length + 1, ev = dockEvaluate(scores, opts.checkin, opts.history, idx);
    await card(s, c => resultScreen(c, 'DOCKMASTER · DEBRIEF', ev, [[`${scores.t3_track_err_px ?? '—'} px`, 'laser tracking error'], [`${scores.t1_order_acc != null ? Math.round(scores.t1_order_acc * 100) + '%' : '—'}`, 'port order accuracy'], [`${scores.t2_accuracy != null ? Math.round(scores.t2_accuracy * 100) + '%' : '—'}`, 'satellite tracking accuracy']]), 'Save and close (SPACE)');
    s.finish(true); await loop;
    return {game: 'dock', session_index: idx, scores, ev, fields: {track_err_px: scores.t3_track_err_px}, result: `tracking error ${scores.t3_track_err_px ?? '—'} px`,
      used: !ev.invalid && idx > DC.FAMILIARISATION_SESSIONS, why: ev.invalid ? 'game asked for a retest' : idx <= DC.FAMILIARISATION_SESSIONS ? 'familiarisation session' : ''};
  }

  /* =================================================================
     GAME 2  STARSIGHT  (vision) - starsight_core.py
     ================================================================= */
  const VC = {VERSION: 'starsight-web-2.0', CS_FREQS: [['wide', 1.5], ['fine', 4.0]], CS_FADE_RATE: 0.30, CS_MIN: 0.004, CS_CONFIRM: 6, CS_WARMUP: 0.20, CS_START_OFFSET: 0.5,
    CS_STEP_HARDER: 0.10, CS_STEP_EASIER: 0.20, CS_SHOW_S: 1.5, CS_TIMEOUT_S: 4.0, CS_GAP_S: 0.7, CS_SIDE_DEG: 6.0, CS_PATCH_DEG: 4.0, CS_SIGMA_DEG: 0.8, CS_TYPICAL: {wide: 1.7, fine: 1.8},
    SS_DIST_MM: 400, SS_START: 0.8, SS_WARMUP: 2, SS_TRIALS: 12, SS_STEP_HARDER: 0.1, SS_STEP_EASIER: 0.2, SS_MIN_LOGMAR: -0.3, SS_MAX_LOGMAR: 1.2, SS_TIMEOUT_S: 6.0, SS_GAP_S: 0.45, SS_TYPICAL: 0.0,
    QUEASY_MAX: 3, BASELINE_MIN: 3, BASELINE_MAX: 10, CS_DROP: 0.25, NA_WORSE: 0.2, GENERIC_CS_LOW: 1.3, GENERIC_NA_HIGH: 0.5};
  const r2 = x => x == null ? null : Math.round(x * 100) / 100, log10 = Math.log10, clampLog = l => Math.max(log10(VC.CS_MIN), Math.min(0, l));
  const DIRS = ['up', 'down', 'left', 'right'];
  class ContrastTest {
    constructor(eye, confirm) { this.eye = eye; this.confirm = confirm; this.trials = []; this.done = false; this.inGap = true; this.gapStart = 0; this.trialStart = 0; this.fi = 0; this.cn = 0; this.level = null; this.fadeLevel = null; this.total = VC.CS_FREQS.length * (1 + confirm); }
    get current() { return this.trials[this.trials.length - 1] || null; }
    get progress() { return Math.min(1, this.trials.length / this.total); }
    _next() {
      if (this.fi >= VC.CS_FREQS.length) return null;
      let [label, freq] = VC.CS_FREQS[this.fi]; const last = this.current;
      if (!last || (last.kind === 'side' && this.cn >= this.confirm)) {
        if (last) { this.fi++; this.cn = 0; if (this.fi >= VC.CS_FREQS.length) return null; [label, freq] = VC.CS_FREQS[this.fi]; }
        return {kind: 'fade', label, freq, tapped: null};
      }
      let warm = false;
      if (last.kind === 'fade') { this.fadeLevel = log10(last.tapped || VC.CS_MIN); this.level = clampLog(log10(Math.max(VC.CS_WARMUP, 10 ** (this.fadeLevel + 0.8)))); warm = true; }
      else if (this.cn === 1) this.level = clampLog(this.fadeLevel + VC.CS_START_OFFSET);
      else this.level = clampLog(this.level + (last.answer === last.side ? -VC.CS_STEP_HARDER : VC.CS_STEP_EASIER));
      this.cn++;
      return {kind: 'side', label, freq, contrast: 10 ** this.level, side: Math.random() < .5 ? 'left' : 'right', warmup: warm, answer: null};
    }
    fadeDur() { return Math.abs(log10(VC.CS_MIN)) / VC.CS_FADE_RATE + 0.5; }
    contrastAt(t) { return Math.max(VC.CS_MIN, 10 ** (-VC.CS_FADE_RATE * t)); }
    finished(tr, t) { return tr.kind === 'fade' ? (tr.tapped != null || t >= this.fadeDur()) : (tr.answer != null || t >= VC.CS_TIMEOUT_S); }
    update(now) { if (this.done) return; if (this.inGap) { if (now - this.gapStart >= VC.CS_GAP_S) { const n = this._next(); if (!n) { this.done = true; return; } this.trials.push(n); this.trialStart = now; this.inGap = false; } return; } if (this.finished(this.current, now - this.trialStart)) { this.inGap = true; this.gapStart = now; } }
    tap(now, side) { if (this.done || this.inGap || !this.current) return; const tr = this.current, t = now - this.trialStart; if (tr.kind === 'fade') { if (tr.tapped == null) tr.tapped = this.contrastAt(t); } else if (tr.answer == null && (side === 'left' || side === 'right')) tr.answer = side; }
    stim(now) { if (this.done || this.inGap || !this.current) return null; const tr = this.current, t = now - this.trialStart; if (tr.kind === 'fade') return tr.tapped != null ? null : {freq: tr.freq, contrast: this.contrastAt(t), side: 'center'}; return t < VC.CS_SHOW_S ? {freq: tr.freq, contrast: tr.contrast, side: tr.side} : null; }
    waitingForSide() { return !this.inGap && this.current && this.current.kind === 'side' && this.current.answer == null; }
    results() {
      const out = {eye: this.eye}, per = [], reasons = [];
      for (const [label] of VC.CS_FREQS) {
        const fades = this.trials.filter(t => t.kind === 'fade' && t.label === label), sides = this.trials.filter(t => t.kind === 'side' && t.label === label && !t.warmup);
        if (!sides.length) { out['cs_' + label] = null; continue; }
        const last = sides.slice(-4), v = r2(-last.reduce((a, t) => a + log10(t.contrast), 0) / last.length); out['cs_' + label] = v; per.push(v);
        const acc = sides.filter(t => t.answer === t.side).length / sides.length;
        if (acc <= 0.5) reasons.push(`${label} signals: answers no better than guessing`);
        if (fades.length && fades[0].tapped && Math.abs(-log10(fades[0].tapped) - v) > 0.6) reasons.push(`${label} signals: fade and side answers disagree`);
      }
      out.cs_mean = per.length ? r2(per.reduce((a, b) => a + b, 0) / per.length) : null; out.cs_quality = per.length && !reasons.length ? 'ok' : 'unreliable'; out.cs_reason = reasons.join('; ');
      return out;
    }
  }
  class SharpTest {
    constructor(eye, quantize, nTrials) { this.eye = eye; this.quantize = quantize; this.trials = []; this.done = false; this.inGap = true; this.gapStart = 0; this.trialStart = 0; this.level = VC.SS_START; this.combo = 0; this.best = null; this.total = VC.SS_WARMUP + nTrials; }
    get current() { return this.trials[this.trials.length - 1] || null; }
    get progress() { return Math.min(1, this.trials.length / this.total); }
    _next() {
      const n = this.trials.length; if (n >= this.total) return null; const last = this.current;
      if (last && n > VC.SS_WARMUP) this.level = last.answer === last.direction ? this.level - VC.SS_STEP_HARDER : this.level + VC.SS_STEP_EASIER;
      this.level = Math.max(VC.SS_MIN_LOGMAR, Math.min(VC.SS_MAX_LOGMAR, this.level));
      const [shown, floor] = this.quantize(this.level), d = choice(DIRS.filter(x => x !== (last && last.direction)));
      return {level: this.level, shown, direction: d, warmup: n < VC.SS_WARMUP, atFloor: floor, answer: null};
    }
    update(now) { if (this.done) return; if (this.inGap) { if (now - this.gapStart >= VC.SS_GAP_S) { const nx = this._next(); if (!nx) { this.done = true; return; } this.trials.push(nx); this.trialStart = now; this.inGap = false; } return; }
      const tr = this.current; if (tr.answer != null || now - this.trialStart >= VC.SS_TIMEOUT_S) { if (tr.answer === tr.direction) { this.combo++; if (!tr.warmup) this.best = this.best == null ? tr.shown : Math.min(this.best, tr.shown); } else this.combo = 0; this.inGap = true; this.gapStart = now; } }
    tap(now, d) { if (!this.done && !this.inGap && this.current && this.current.answer == null && DIRS.includes(d)) this.current.answer = d; }
    target() { return this.done || this.inGap ? null : this.current; }
    results() {
      const warm = this.trials.filter(t => t.warmup), scored = this.trials.filter(t => !t.warmup), r = {eye: this.eye};
      if (!scored.length) return Object.assign(r, {na_logmar: null, na_snellen: null, na_floor: 0, na_best: null, na_quality: 'unreliable', na_reason: 'no answers'});
      const last = scored.slice(-6), lm = r2(last.reduce((a, t) => a + t.shown, 0) / last.length), acc = scored.filter(t => t.answer === t.direction).length / scored.length;
      const floor = last.filter(t => t.atFloor).length >= 3 && acc >= 0.6 ? 1 : 0, reasons = [];
      if (warm.filter(t => t.answer === t.direction).length < warm.length) reasons.push('missed an easy warm-up target');
      if (acc <= 0.35) reasons.push('answers no better than guessing');
      return Object.assign(r, {na_logmar: lm, na_snellen: Math.round(20 * 10 ** lm), na_floor: floor, na_best: r2(this.best), na_accuracy: Math.round(acc * 100) / 100, na_quality: reasons.length ? 'unreliable' : 'ok', na_reason: reasons.join(', ')});
    }
  }
  const snellen = lm => lm == null ? null : `20/${Math.round(20 * 10 ** lm)}`;
  function buildRow(Rr, Ll, meta) {
    const row = {...meta}; const keys = ['cs_wide', 'cs_fine', 'cs_mean', 'cs_quality', 'cs_reason', 'na_logmar', 'na_snellen', 'na_floor', 'na_best', 'na_quality', 'na_reason'];
    for (const [e, x] of [['R', Rr], ['L', Ll]]) for (const k of keys) row[`${k}_${e}`] = x[k] ?? null;
    const both = k => Rr[k] != null && Ll[k] != null;
    row.eye_gap_cs = both('cs_mean') ? r2(Math.abs(Rr.cs_mean - Ll.cs_mean)) : null; row.eye_gap_na = both('na_logmar') ? r2(Math.abs(Rr.na_logmar - Ll.na_logmar)) : null;
    row.vision_score = both('cs_mean') ? r2((Rr.cs_mean + Ll.cs_mean) / 2) : null;
    const allOk = [Rr.cs_quality, Ll.cs_quality, Rr.na_quality, Ll.na_quality].every(qq => qq === 'ok');
    row.valid = allOk && (meta.queasy || 0) <= VC.QUEASY_MAX ? 1 : 0; return row;
  }
  function visionBaseline(history) {
    const use = history.filter(h => +(h.valid || 0) === 1 && h.data_source !== 'practice').slice(-VC.BASELINE_MAX); if (use.length < VC.BASELINE_MIN) return null;
    const b = {n: use.length, n_sim: use.filter(h => h.data_source === 'simulated').length};
    for (const k of ['cs_mean_R', 'cs_mean_L', 'na_logmar_R', 'na_logmar_L']) { const v = use.map(h => num(h[k])).filter(x => x != null); if (v.length >= VC.BASELINE_MIN) b[k] = median(v); }
    return b;
  }
  function evaluateVision(row, history) {
    const base = visionBaseline(history), notes = [], flags = {R: [], L: []}, nm = {R: 'RIGHT', L: 'LEFT'};
    if ((row.queasy || 0) > VC.QUEASY_MAX) notes.push(`you reported feeling queasy (${row.queasy}/10): nausea makes vision tests unreliable`);
    for (const e of ['R', 'L']) { if (row[`cs_quality_${e}`] !== 'ok') notes.push(`${nm[e]} eye, Ghost Signals: ${row[`cs_reason_${e}`] || 'unreliable'}`); if (row[`na_quality_${e}`] !== 'ok') notes.push(`${nm[e]} eye, Sharp Shooter: ${row[`na_reason_${e}`] || 'unreliable'}`); if (row[`na_floor_${e}`]) notes.push(`${nm[e]} eye reached this screen's smallest letter`); }
    let mode;
    if (base) { mode = 'personal'; for (const e of ['R', 'L']) { const cs = row[`cs_mean_${e}`], bc = base[`cs_mean_${e}`]; if (cs != null && bc != null && bc - cs >= VC.CS_DROP) flags[e].push(['cs', `faint-vision score dropped ${r2(bc - cs)} log units vs your normal (${r2(bc)} → ${cs})`]);
      const na = row[`na_logmar_${e}`], bn = base[`na_logmar_${e}`]; if (na != null && bn != null && na - bn >= VC.NA_WORSE) flags[e].push(['na', `near vision ${Math.round((na - bn) * 10)} lines worse than your normal (${snellen(bn)} → ${snellen(na)})`]); } }
    else { mode = 'generic'; for (const e of ['R', 'L']) { const cs = row[`cs_mean_${e}`], na = row[`na_logmar_${e}`]; if (cs != null && cs < VC.GENERIC_CS_LOW) flags[e].push(['cs', `faint-vision score ${cs} is below the rough screen reference (${VC.GENERIC_CS_LOW})`]); if (na != null && na > VC.GENERIC_NA_HIGH) flags[e].push(['na', `near vision ${snellen(na)} is blurrier than the rough reference`]); } }
    const csE = ['R', 'L'].filter(e => flags[e].some(([k]) => k === 'cs')), naE = ['R', 'L'].filter(e => flags[e].some(([k]) => k === 'na')), names = es => es.map(e => nm[e]).join(' and ');
    let status, headline, message;
    if (!row.valid) [status, headline, message] = ['RETEST', 'Not reliable today: retest', "This check is greyed out and won't be used for your baseline."];
    else if (mode === 'personal' && csE.length) { status = 'SCAN NOW'; headline = `Request an eye scan (OCT) for the ${names(csE)} eye`; message = csE.length === 1 ? `Only the ${nm[csE[0]]} eye lost faint vision, while the other eye stayed normal. Screen or lighting problems would affect both eyes, so this looks like a real eye change.` : 'Both eyes lost faint vision. Retest once in better conditions; if it repeats, request an eye scan.'; if (naE.length) message += ` Near vision is also worse in the ${names(naE)} eye: try your space anticipation glasses.`; }
    else if (mode === 'personal' && naE.length) [status, headline, message] = ['GLASSES', `Near vision worse in the ${names(naE)} eye`, 'Close-up blur is the most common SANS change. Try your space anticipation glasses and retest tomorrow. If it keeps getting worse, tell the flight surgeon.'];
    else if (csE.length || naE.length) [status, headline, message] = ['CHECK', 'Outside the rough reference: retest tomorrow', "Your personal baseline isn't ready yet, so this compares you with rough screen values only."];
    else { status = 'GO'; headline = base ? 'Both eyes match your normal' : 'Looks fine: your baseline is still forming'; message = base ? 'Faint vision and near vision are within your usual range.' : `Valid scans so far: ${history.filter(h => +(h.valid || 0) === 1).length + 1}/${VC.BASELINE_MIN} before your personal baseline turns on.`; }
    const conf = !row.valid ? 'LOW' : base && base.n >= 5 ? 'HIGH' : base ? 'MEDIUM' : 'LOW', why = !row.valid ? 'unreliable session' : base ? `personal baseline from ${base.n} sessions` : 'no personal baseline yet';
    return {status, headline, message, reasons: [...flags.R.map(f => 'RIGHT eye: ' + f[1]), ...flags.L.map(f => 'LEFT eye: ' + f[1]), ...notes], conf, why, invalid: !row.valid};
  }
  async function playStarsight(opts) {
    const q = opts.quick, s = stage('GAME 2 · STARSIGHT · vision', 'physical'), store = opts.store;
    const loop = s.loop(() => {});
    const CARD_W = 85.6, CARD_H = 53.98;
    let calib = store.get();
    const W = () => s.W, H = () => s.H;
    const d2p = deg => Math.tan(deg * Math.PI / 180) * calib.dist * calib.ppmm;
    const fits = (ppmm, d) => { const f = deg => Math.tan(deg * Math.PI / 180) * d * ppmm; return f(VC.CS_SIDE_DEG + VC.CS_PATCH_DEG / 2 + .5) < W() / 2 - 10 && f(VC.CS_PATCH_DEG / 2 + 2) < H() / 2 - 40; };
    const ePixels = lm => { const arcmin = 5 * 10 ** lm, hpx = 2 * VC.SS_DIST_MM * Math.tan(arcmin / 60 * Math.PI / 180 / 2) * calib.ppmm, stroke = Math.max(1, Math.round(hpx / 5)), shownMm = 5 * stroke / calib.ppmm;
      const shown = log10(2 * Math.atan(shownMm / (2 * VC.SS_DIST_MM)) * 180 / Math.PI * 60 / 5); return [stroke, Math.round(shown * 1000) / 1000, stroke === 1 && hpx / 5 < 1]; };
    // ---- pre-check: queasy + glasses
    const pre = await new Promise(resolve => {
      let queasy = null, glasses = null, hits = [], live = true;
      s.on('down', p => { for (const [r, f] of hits) if (p.x >= r[0] && p.x <= r[0] + r[2] && p.y >= r[1] && p.y <= r[1] + r[3]) f(); });
      s.on('key', null);
      const step = () => { if (s.done) return resolve(null); const c = s.begin(), w = W(), cx = w / 2; space(c, w, H()); hits = [];
        text(c, 'Eyes on the stars, pilot.', cx, 90, 36, COL.text, {bold: true}); wrapText(c, 'Two quick vision games watch for SANS, the eye changes many astronauts get in space. Each eye is compared with its own normal and with the other eye.', cx, 140, Math.min(900, w - 60), 18, COL.muted);
        text(c, 'FEELING QUEASY / SPACE-SICK NOW?  (0 = NOT AT ALL, 10 = VERY)', cx, 230, 14, COL.muted, {mono: true});
        for (let v = 0; v <= 10; v++) { const r = [cx - 11 * 23 + v * 46, 250, 40, 36]; rrect(c, ...r, 18, queasy === v ? COL.accent : '#0a1120', queasy === v ? COL.accent : COL.line); text(c, String(v), r[0] + 20, r[1] + 18, 16, queasy === v ? '#04111d' : COL.text); hits.push([r, () => { queasy = v; }]); }
        text(c, 'WEARING YOUR USUAL GLASSES / LENSES?', cx, 330, 14, COL.muted, {mono: true});
        [['yes', 'Yes / don’t need them', -130], ['no', 'No', 110]].forEach(([k, l, dx]) => { const r = [cx + dx - 100, 350, 200, 38]; rrect(c, ...r, 19, glasses === k ? COL.accent : '#0a1120', glasses === k ? COL.accent : COL.line); text(c, l, r[0] + 100, r[1] + 19, 15, glasses === k ? '#04111d' : COL.text); hits.push([r, () => { glasses = k; }]); });
        if (queasy != null && queasy > VC.QUEASY_MAX) text(c, 'Too queasy: results will be greyed out (nausea skews vision tests)', cx, 420, 15, COL.amber);
        const ok = queasy != null && glasses != null, r = [cx - 120, H() - 110, 240, 54]; rrect(c, ...r, 12, ok ? COL.accent : '#3c465f'); text(c, 'Continue', cx, r[1] + 27, 22, ok ? '#031018' : COL.muted, {bold: true});
        if (ok) hits.push([r, () => { live = false; s.on('down', null); resolve({queasy, glasses}); }]);
        if (!s.done && live) requestAnimationFrame(() => { if (live) step(); });
      };
      step();
    });
    if (!pre || s.done) { s.finish && s.finish(null); return null; }
    // ---- calibration (once; redo if it no longer fits this screen)
    if (!calib || !fits(calib.ppmm, calib.dist)) {
      const got = await new Promise(resolve => {
        let cardW = 324, dist_ = 500, drag = false, hits = [], track = null, live = true;
        s.on('down', p => { if (track && Math.abs(p.y - track[1]) < 24 && p.x >= track[0] - 20 && p.x <= track[0] + track[2] + 20) { drag = true; cardW = 150 + Math.max(0, Math.min(1, (p.x - track[0]) / track[2])) * 750; } for (const [r, f] of hits) if (p.x >= r[0] && p.x <= r[0] + r[2] && p.y >= r[1] && p.y <= r[1] + r[3]) f(); });
        s.on('up', () => { drag = false; });
        s.on('key', code => { if (code === 'ArrowLeft') cardW -= 2; if (code === 'ArrowRight') cardW += 2; });
        const step = () => { if (s.done) return resolve(null); if (!live) return; if (drag && track) cardW = 150 + Math.max(0, Math.min(1, (s.mouse.x - track[0]) / track[2])) * 750; cardW = Math.max(150, Math.min(900, cardW));
          const c = s.begin(), w = W(), cx = w / 2; space(c, w, H()); hits = [];
          text(c, 'ONE-TIME SETUP · 30 SECONDS', cx, 50, 14, COL.gold, {mono: true}); text(c, 'Teach the screen real sizes', cx, 84, 30, COL.text, {bold: true});
          text(c, 'Hold a bank or ID card flat against the screen. Drag the slider (or use ← →) until the box matches the card exactly.', cx, 118, 16, COL.muted);
          const ch = cardW * CARD_H / CARD_W; rrect(c, cx - cardW / 2, 140, cardW, ch, 12, '#28240f', COL.gold, 3); text(c, 'CARD', cx, 140 + ch / 2, 14, COL.gold, {mono: true});
          const ty = 140 + ch + 30; track = [cx - 260, ty, 520, 8]; rrect(c, ...track, 4, COL.line); circle(c, track[0] + (cardW - 150) / 750 * track[2], ty + 4, 13, COL.accent);
          text(c, 'How far will you sit? (eye to screen)', cx, ty + 36, 14, COL.muted, {mono: true});
          [300, 400, 500, 600].forEach((d, k) => { const r = [cx - 250 + k * 130, ty + 52, 120, 34]; rrect(c, ...r, 17, d === dist_ ? COL.accent : '#0a1120', d === dist_ ? COL.accent : COL.line); text(c, `${d / 10} cm`, r[0] + 60, r[1] + 17, 15, d === dist_ ? '#04111d' : COL.text); hits.push([r, () => { dist_ = d; }]); });
          const ppmm = cardW / CARD_W, ok = fits(ppmm, dist_);
          text(c, ok ? `Fits this screen at ${dist_ / 10} cm` : `Too big for this screen at ${dist_ / 10} cm: pick a shorter distance`, cx, ty + 110, 17, ok ? COL.green : COL.amber);
          const r = [cx - 100, ty + 136, 200, 50]; rrect(c, ...r, 12, ok ? COL.accent : '#3c465f'); text(c, 'Done', cx, r[1] + 25, 20, ok ? '#031018' : COL.muted, {bold: true});
          if (ok) hits.push([r, () => { live = false; s.on('down', null); s.on('up', null); s.on('key', null); resolve({ppmm, dist: dist_}); }]);
          if (live) requestAnimationFrame(step); };
        step();
      });
      if (!got || s.done) { s.finish && s.finish(null); return null; }
      calib = got; store.set(calib);
    }
    const gaborCache = new Map();
    function gabor(freq, contrast) {
      const ppd = d2p(1), size = Math.max(8, Math.round(VC.CS_PATCH_DEG * ppd)), key = `${freq}|${contrast.toFixed(5)}|${size}`;
      const cv = document.createElement('canvas'); cv.width = cv.height = size; const cx2 = cv.getContext('2d'), img = cx2.createImageData(size, size), sig = VC.CS_SIGMA_DEG * ppd;
      for (let i = 0; i < size; i++) for (let j = 0; j < size; j++) { const x = i - size / 2, y = j - size / 2, env = Math.exp(-(x * x + y * y) / (2 * sig * sig));
        const lum = Math.max(0, Math.min(255, Math.round(128 + 127.5 * contrast * Math.sin(2 * Math.PI * freq * x / ppd) * env + (Math.random() - .5)))); const o = (j * size + i) * 4; img.data[o] = img.data[o + 1] = img.data[o + 2] = lum; img.data[o + 3] = 255; }
      cx2.putImageData(img, 0, 0); return cv;
    }
    function drawE(c, x, y, stroke, dir, color = '#000') {
      const cells = [[0, 0], [0, 1], [0, 2], [0, 3], [0, 4]]; for (const r of [0, 2, 4]) for (let k = 1; k < 5; k++) cells.push([k, r]);
      const rot = {right: (cc, rr) => [cc, rr], left: (cc, rr) => [4 - cc, rr], down: (cc, rr) => [rr, cc], up: (cc, rr) => [rr, 4 - cc]}[dir];
      const x0 = Math.round(x - 2.5 * stroke), y0 = Math.round(y - 2.5 * stroke); c.fillStyle = color; for (const [cc, rr] of cells) { const [a, b] = rot(cc, rr); c.fillRect(x0 + a * stroke, y0 + b * stroke, stroke, stroke); }
    }
    const res = {}; let step = 0;
    const BRIEF = {
      1: ['ROUND 1 OF 2 · FAINT VISION', 'GHOST SIGNALS', ['A signal (soft stripes) appears in the middle and slowly fades. Press SPACE or click the moment it’s gone.', 'Then signals flash inside one of two portholes. Click the porthole (left / right half) or press ← / →.', 'They get very faint on purpose. Can’t see it? Guess. Keep looking at the centre dot. One eye at a time.']],
      2: ['ROUND 2 OF 2 · NEAR VISION', 'SHARP SHOOTER', ['Bring the screen to 40 cm: elbow to fingertips. Wear your usual reading glasses if you use them.', 'An E appears in the scope. Which way do its three arms point? Arrow keys / WASD, swipe, or click the arrow buttons.', 'Hit = smaller next time, miss = bigger. Too tiny? Guess! That’s how we find your limit.']]};
    for (const rnum of [1, 2]) {
      await card(s, (c, w, h) => { const cx = w / 2; text(c, BRIEF[rnum][0], cx, 90, 14, COL.gold, {mono: true}); text(c, BRIEF[rnum][1], cx, 130, 40, COL.accent, {bold: true}); let y = 200; for (const l of BRIEF[rnum][2]) y = wrapText(c, '• ' + l, cx, y, Math.min(860, w - 80), 19, COL.text) + 10; if (q) text(c, 'QUICK VERSION · fewer trials', cx, 60, 14, COL.gold, {bold: true, mono: true}); }, 'Got it (SPACE)');
      if (s.done) return null;
      for (const eye of ['right', 'left']) {
        const cover = eye === 'right' ? 'LEFT' : 'RIGHT';
        await card(s, (c, w) => { const cx = w / 2; circle(c, cx, 190, 80, '#1b2846', COL.accent, 3); circle(c, cx - 32, 176, 9, COL.text); circle(c, cx + 32, 176, 9, COL.text); rrect(c, (cover === 'LEFT' ? cx - 32 : cx + 32) - 38, 148, 76, 56, 24, COL.amber); text(c, 'COVER', cover === 'LEFT' ? cx - 32 : cx + 32, 176, 13, '#3a2600', {bold: true, mono: true});
          text(c, `Testing your ${eye.toUpperCase()} eye`, cx, 320, 34, COL.text, {bold: true});
          wrapText(c, `Cover your ${cover} eye with your palm (don’t press on it). ` + (rnum === 1 ? `Sit ${calib.dist / 10} cm from the screen.` : 'Bring the screen to 40 cm.') + ' Screen brightness up, same room light as usual.', cx, 370, Math.min(820, w - 80), 19, COL.text); }, 'Ready (SPACE)');
        if (s.done) return null;
        const t0 = performance.now() / 1000, now = () => performance.now() / 1000 - t0;
        const r = await new Promise(resolve => {
          if (rnum === 1) {
            const test = new ContrastTest(eye, q ? 3 : VC.CS_CONFIRM); let patch = null, pkey = null, fb = null;
            s.on('key', code => { const t = now(); if (test.waitingForSide()) { if (t - test.trialStart < .25) return; const side = code === 'ArrowLeft' || code === 'KeyF' ? 'left' : code === 'ArrowRight' || code === 'KeyJ' ? 'right' : null; if (side) { const cur = test.current; test.tap(t, side); fb = [t, cur.answer === cur.side ? (cur.warmup ? 'WARM-UP OK' : 'SIGNAL LOCKED') : 'NOISE ✕', cur.answer === cur.side ? COL.green : COL.red]; } }
              else if (code === 'Space' && test.current && test.current.kind === 'fade' && !test.inGap) { test.tap(t); fb = [t, 'GOT IT', COL.green]; } });
            s.on('down', p => { const t = now(); if (test.waitingForSide()) { if (t - test.trialStart < .25) return; if (Math.abs(p.x - W() / 2) < d2p(VC.CS_SIDE_DEG) * .5) { fb = [t, '‹ TAP A PORTHOLE ›', COL.amber]; return; } const cur = test.current; test.tap(t, p.x < W() / 2 ? 'left' : 'right'); fb = [t, cur.answer === cur.side ? (cur.warmup ? 'WARM-UP OK' : 'SIGNAL LOCKED') : 'NOISE ✕', cur.answer === cur.side ? COL.green : COL.red]; }
              else if (test.current && test.current.kind === 'fade' && !test.inGap) { test.tap(t); fb = [t, 'GOT IT', COL.green]; } });
            const frame = () => { if (s.done) return resolve(null); const t = now(); test.update(t); const c = s.begin(), w = W(), h = H(), cx = w / 2, cy = h / 2, off = d2p(VC.CS_SIDE_DEG), rr = d2p(VC.CS_PATCH_DEG / 2);
              c.fillStyle = 'rgb(128,128,128)'; c.fillRect(0, 0, w, h);
              const st = test.stim(t);
              if (st) { const key = st.side === 'center' ? `f${Math.round(st.contrast * 1e4)}` : `${st.freq}|${st.contrast}|${test.trials.length}`; if (key !== pkey) { patch = gabor(st.freq, st.contrast); pkey = key; } const px = cx + (st.side === 'left' ? -off : st.side === 'right' ? off : 0); c.drawImage(patch, Math.round(px - patch.width / 2), Math.round(cy - patch.height / 2)); }
              if (test.current && test.current.kind === 'side') { for (const sx of [-1, 1]) circle(c, cx + sx * off, cy, rr, null, 'rgb(162,162,162)', 2); if (test.waitingForSide()) { text(c, '‹ LEFT', cx - off, cy + rr + 22, 15, '#d8d8d8', {mono: true}); text(c, 'RIGHT ›', cx + off, cy + rr + 22, 15, '#d8d8d8', {mono: true}); } }
              circle(c, cx, cy, 5, '#000');
              if (fb && t - fb[0] < .75) { c.globalAlpha = 1 - (t - fb[0]) / .75; text(c, fb[1], cx, 40, 28, fb[2], {bold: true, mono: true}); c.globalAlpha = 1; }
              const cur = test.current; s.status(test.done ? '' : test.inGap || !cur ? 'get ready...' : cur.kind === 'fade' ? `${cur.label.toUpperCase()} SIGNAL FADING: tap when it's gone` : `${cur.label.toUpperCase()} SIGNAL: which porthole?` + (cur.warmup ? ' (warm-up)' : ''));
              s.progress((step + test.progress) / 4);
              if (test.done) { s.on('key', null); s.on('down', null); return resolve(test.results()); }
              requestAnimationFrame(frame); };
            requestAnimationFrame(frame);
          } else {
            const test = new SharpTest(eye, lm => ePixels(lm).slice(1), q ? 6 : VC.SS_TRIALS); let fb = null, downAt = null, hits = 0;
            const keymap = {ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down', ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right'};
            const fire = d => { const t = now(), tg = test.target(); if (!d || !tg || t - test.trialStart < .2) return; test.tap(t, d); if (tg.answer === tg.direction) { hits++; fb = [t, tg.warmup ? 'WARM-UP HIT' : 'TARGET LOCKED', COL.green]; } else fb = [t, 'MISSED', COL.red]; };
            let btns = {};
            s.on('key', code => fire(keymap[code]));
            s.on('down', p => { const b = Object.entries(btns).find(([, r]) => p.x >= r[0] && p.x <= r[0] + r[2] && p.y >= r[1] && p.y <= r[1] + r[3]); if (b) fire(b[0]); else downAt = p; });
            s.on('up', p => { if (!downAt) return; const dx = p.x - downAt.x, dy = p.y - downAt.y; if (Math.max(Math.abs(dx), Math.abs(dy)) > 40) fire(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up')); downAt = null; });
            const frame = () => { if (s.done) return resolve(null); const t = now(); test.update(t); const c = s.begin(), w = W(), h = H(), cx = w / 2, cy = h / 2 - 10, sr = Math.min(150, h / 2 - 110);
              space(c, w, h); circle(c, cx, cy, sr, '#f5f5f5', test.target() ? COL.gold : COL.line, 4);
              const tg = test.target(); if (tg) drawE(c, cx, cy, ePixels(tg.level)[0], tg.direction);
              btns = {up: [cx - 32, cy - sr - 84, 64, 64], down: [cx - 32, cy + sr + 20, 64, 64], left: [cx - sr - 84, cy - 32, 64, 64], right: [cx + sr + 20, cy - 32, 64, 64]};
              for (const [d, r] of Object.entries(btns)) { rrect(c, ...r, 14, COL.panel2, COL.line, 2); text(c, {up: '▲', down: '▼', left: '◀', right: '▶'}[d], r[0] + 32, r[1] + 32, 24, COL.text); }
              text(c, `TARGETS LOCKED  ${hits}`, 30, 40, 15, COL.green, {mono: true, align: 'left'});
              text(c, '40 cm from the screen · arrow keys / WASD / swipe / buttons', cx, h - 24, 14, COL.muted, {mono: true});
              if (fb && t - fb[0] < .75) { c.globalAlpha = 1 - (t - fb[0]) / .75; text(c, fb[1], cx, 40, 28, fb[2], {bold: true, mono: true}); c.globalAlpha = 1; }
              s.status(test.done ? '' : test.inGap ? 'next target incoming...' : (test.current && test.current.warmup ? 'WARM-UP TARGET: ' : '') + 'which way do the arms point?'); s.progress((step + test.progress) / 4);
              if (test.done) { s.on('key', null); s.on('down', null); s.on('up', null); return resolve(test.results()); }
              requestAnimationFrame(frame); };
            requestAnimationFrame(frame);
          }
        });
        if (!r || s.done) { s.finish && s.finish(null); return null; }
        res[`${rnum}|${eye}`] = r; step++;
      }
    }
    const Rr = {...res['1|right'], ...res['2|right']}, Ll = {...res['1|left'], ...res['2|left']};
    const row = buildRow(Rr, Ll, {data_source: q ? 'quick' : 'prototype_gameplay', version: VC.VERSION, queasy: pre.queasy, glasses: pre.glasses});
    const ev = evaluateVision(row, opts.history);
    row.status = ev.status;
    await card(s, (c, w) => { const sx = (w - 1280) / 2; c.save(); c.translate(Math.max(0, sx), 0); resultScreen(c, 'STARSIGHT · VISION DEBRIEF', ev, [[`${row.vision_score ?? '—'}`, 'faint vision, logCS (both eyes)'], [`${row.cs_mean_R ?? '—'} / ${row.cs_mean_L ?? '—'}`, 'faint vision right / left'], [`${snellen(row.na_logmar_R) || '—'} / ${snellen(row.na_logmar_L) || '—'}`, 'near vision right / left']]); c.restore(); }, 'Save and close (SPACE)');
    s.finish(true); await loop;
    return {game: 'starsight', session_index: opts.sessionIndex || opts.history.length + 1, scores: row, ev, fields: {vision_score: row.vision_score}, result: `faint vision ${row.vision_score ?? '—'} logCS`, used: !!row.valid, why: row.valid ? '' : 'game asked for a retest'};
  }

  async function play(name, opts) {
    try { return await ({orbit: playOrbit, starsight: playStarsight, dock: playDock}[name])(opts); }
    catch (e) { console.error(e); document.querySelectorAll('.game-overlay').forEach(x => x.remove()); return null; }
  }
  return {play, _test: {orbitScore, orbitEvaluate, dockScore, dockEvaluate, ContrastTest, SharpTest, buildRow, evaluateVision, orbitSchedule, dockGen}};
})();
