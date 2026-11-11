const $ = s => document.querySelector(s);
const el = {panel: $('#panel'), head: $('#panel-head'), log: $('#log'), status: $('#status'), form: $('#form'),
  message: $('#message'), send: $('#send'), mic: $('#mic'), model: $('#model'), follow: $('#follow'),
  pitch: $('#pitch'), rate: $('#rate'), volume: $('#volume'), zoom: $('#zoom'), initiative: $('#initiative'), presence: $('#presence'), bargein: $('#bargein'), speak: $('#speak'), lang: $('#lang'), handsfree: $('#handsfree'), bg: $('#bg'),
  uilang: $('#uilang'), agent: $('#agent'), control: $('#control'), work: $('#work'), confirm: $('#confirm'), drag: $('#drag'), voicenative: $('#voicenative'), camera: $('#camera'), cam: $('#cam'), subtitle: $('#subtitle'), openChat: $('#open-chat')};

// ---- settings (per-viewer convenience; app works without storage) ----
// Settings live in ui-state.json next to the app (the server hands them over with the page): the desktop window gets a new
// address on every launch, and browser storage is per address, so it alone would forget everything on restart.
const saved = (() => {
  if (window.APP_STATE && Object.keys(window.APP_STATE).length) return window.APP_STATE;
  try { return JSON.parse(localStorage.getItem('companion') || '{}'); } catch { return {}; }
})();
let settingsReady = false, saveTimer = null, hearRestoring = false;   // nothing is written before the saved values have been applied
setUiLang(saved.ui || 'en');   // English by default
el.uilang.value = uiLang;
function collectState() {
  return {model: el.model.value, follow: el.follow.checked,
      pitch: el.pitch.value, rate: el.rate.value, volume: el.volume.value, zoom: el.zoom.value, initiative: el.initiative.checked, presence: el.presence.checked, bargein: el.bargein.checked, speak: el.speak.checked, lang: el.lang.value, streamChannel: ($('#stream-channel') || {}).value || '',
      handsfree: el.handsfree.checked, bg: el.bg.value, closed: el.panel.hidden,
      minimized: el.panel.classList.contains('minimized'), anchor, place: avatar.place,
      ui: uiLang, agent: el.agent.checked, control: el.control.checked, work: el.work.checked, drag: el.drag.checked, voicenative: el.voicenative.checked,
      hearkeep: !!($('#hearkeep') && $('#hearkeep').checked), hearon: !!($('#hearkeep') && $('#hearkeep').checked && $('#hear') && $('#hear').checked)};
}
function persist() {
  if (!settingsReady) return;
  try { localStorage.setItem('companion', JSON.stringify(collectState())); } catch { /* storage unavailable */ }
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSettings, 300);
}
function flushSettings() {
  clearTimeout(saveTimer);
  const body = JSON.stringify(collectState());
  fetch('/state', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json', 'X-App-Token': window.APP_TOKEN}, body}).catch(() => {});
}
addEventListener('pagehide', () => { if (settingsReady) flushSettings(); });

// ---- api ----
async function api(path, data, signal) {
  const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-App-Token': window.APP_TOKEN},
    body: JSON.stringify(data), signal});
  if (!r.ok) {
    let msg = t('err.request');
    try { msg = (await r.json()).error || msg; } catch { /* not json */ }
    throw Error(fixErr(msg));
  }
  return r;
}
function setStatus(text, error = false) { el.status.textContent = text; el.status.className = error ? 'error' : ''; }

// ---- avatar + audio pipeline ----
const avatar = new Avatar($('#stage'));
if (window.APP_MOOD) avatar.mood = window.APP_MOOD;
let audioCtx, analyser, audioEl, levelTimer, emotionTimer;

function ensureAudio() {
  if (audioCtx) { audioCtx.resume(); return; }
  audioCtx = new AudioContext();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  audioEl = new Audio();
  audioCtx.createMediaElementSource(audioEl).connect(analyser);
  analyser.connect(audioCtx.destination);
}

let slowVoice = 0;
function trackLevel() {
  slowVoice = 0;
  const buf = new Float32Array(analyser.fftSize);
  const spec = new Uint8Array(analyser.frequencyBinCount);
  const binHz = audioCtx.sampleRate / analyser.fftSize;
  const tick = () => {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    avatar.level = Math.sqrt(sum / buf.length);
    if (performing && avatar.level > 0.01) {   // music: loudness hardly changes, so the mouth follows the voice band and its quick changes
      analyser.getByteFrequencyData(spec);
      let v = 0, n = 0;
      for (let i = Math.ceil(250 / binHz); i < Math.min(spec.length, Math.floor(3500 / binHz)); i++) { v += spec[i]; n++; }
      v = n ? v / n / 255 : 0;
      slowVoice += (v - slowVoice) * 0.04;
      avatar.level = Math.min(0.4, 0.03 + 0.08 * v + 1.6 * Math.max(0, v - slowVoice * 0.95));
    }
    if (avatar.level > 0.01) {
      // spectral centroid of the voice band: low = round vowels (o, u), high = wide ones (i, e)
      analyser.getByteFrequencyData(spec);
      let w = 0, m = 0;
      for (let i = Math.ceil(250 / binHz); i < Math.min(spec.length, Math.floor(4500 / binHz)); i++) { w += spec[i]; m += spec[i] * i * binHz; }
      if (w > 0) avatar.vowel = Math.max(-0.6, Math.min(0.8, (m / w - 1500) / 1200));
    }
    levelTimer = requestAnimationFrame(tick);
  };
  cancelAnimationFrame(levelTimer);
  tick();
}

let endSpeech = null;   // resolves the playSpeech in progress: a pause event does not come when the audio is already paused
function stopSpeaking() {
  const done = endSpeech; endSpeech = null;
  if (audioEl) { audioEl.pause(); audioEl.removeAttribute('src'); }
  cancelAnimationFrame(levelTimer);
  avatar.speaking = false;
  avatar.level = 0;
  avatar.stopScript();
  el.subtitle.classList.remove('show');
  if (done) done();
}

const estimateSeconds = text => Math.max(2, text.length * 0.065);

/* Synthesize the text; returns a playable object URL. */
async function fetchSpeech(text, emotion = 'neutral') {
  let last;
  for (let attempt = 0; attempt < 2; attempt++) {   // one more try: a sentence that fails once would otherwise only appear as a subtitle
    try {
      const resp = await api('/tts', {text, pitch: Number(el.pitch.value), rate: Number(el.rate.value), emotion, native: el.voicenative.checked});
      const blob = await resp.blob();
      if (blob.size) return URL.createObjectURL(blob);
      last = Error(t('err.audio'));
    } catch (err) { last = err; }
    await new Promise(r => setTimeout(r, 500));
  }
  throw last;
}

/* Play synthesized speech and perform the script's directions in time with it. */
async function playSpeech(url, text, cues) {
  ensureAudio();
  stopSpeaking();
  audioEl.src = url;
  audioEl.volume = Number(el.volume.value);
  try {
    await new Promise((resolve, reject) => {
      audioEl.onended = resolve;
      endSpeech = resolve;
      audioEl.onpause = resolve;   // interrupted
      audioEl.onerror = () => reject(Error(t('err.audio')));
      audioEl.play().then(() => {
        avatar.thinking = false;
        avatar.speaking = true;
        trackLevel();
        const d = audioEl.duration;
        avatar.playScript(cues, isFinite(d) && d > 0 ? d : estimateSeconds(text), () => audioEl.currentTime);
      }, reject);
    });
  } finally {
    audioEl.onpause = null;
    URL.revokeObjectURL(url);
    stopSpeaking();
  }
}

async function speak(text, cues = []) { return playSpeech(await fetchSpeech(text), text, cues); }

/* No audio (muted or voice failed): still act the script out, paced by an estimate. Returns seconds. */
function performSilently(text, cues) {
  const dur = estimateSeconds(text), start = performance.now();
  avatar.thinking = false;
  avatar.playScript(cues, dur, () => (performance.now() - start) / 1000);
  setTimeout(() => avatar.stopScript(), dur * 1000);
  return dur;
}

// ---- hands: she asks, you confirm, the server opens only what actions.json lists ----
let confirmTimer = null;
/* One question with buttons: items = [{label, sub, run}]. Nothing happens unless a button is pressed. */
function askChoice(text, items, onNo) {
  const box = el.confirm;
  const close = () => { clearTimeout(confirmTimer); box.hidden = true; };
  box.replaceChildren();
  const q = document.createElement('span');
  q.id = 'confirm-text';
  q.textContent = text;
  box.append(q);
  for (const [i, it] of items.entries()) {
    const b = document.createElement('button');
    b.className = i === 0 || items.length > 1 ? 'primary' : '';
    b.textContent = it.label;
    if (it.sub) b.title = it.sub;
    b.onclick = () => { close(); it.run(); };
    box.append(b);
    if (it.sub && items.length > 1) { const s = document.createElement('small'); s.textContent = it.sub; b.append(document.createElement('br'), s); }
  }
  const no = document.createElement('button');
  no.textContent = t('act.no');
  no.onclick = () => { close(); onNo?.(); };
  box.append(no);
  box.hidden = false;
  clearTimeout(confirmTimer);
  confirmTimer = setTimeout(() => { close(); onNo?.(); }, 60000);   // an unanswered request lapses by itself
}

async function runAct(body, label) {
  try { await api('/act', body); addMessage('note', t('act.done').replace('{x}', label)); }
  catch (e) { addMessage('note', t('act.fail').replace('{x}', label) + ' (' + e.message + ')'); }
}

function askAction(act) {   // a fixed entry of actions.json
  askChoice(t('act.ask').replace('{x}', act.label), [{label: t('act.yes'), run: () => runAct({id: act.id}, act.label)}]);
}

function askFound(c) {   // something she looked for: the creator says whether it is the right one
  const items = c.items.map(x => ({label: x.label, sub: x.where, run: () => runAct({token: x.token}, x.label)}));
  if (c.search) askChoice(t('act.search').replace('{x}', c.query), [{label: t('act.yes'), run: items[0].run}]);
  else if (items.length === 1) askChoice(t('act.ask').replace('{x}', items[0].label + (c.items[0].where ? ' (' + c.items[0].where + ')' : '')), [{label: t('act.yes'), run: items[0].run}]);
  else askChoice(t('act.which'), items);
}

// ---- code: blocks of her reply are shown (and can be copied) but never spoken; a file is shown to her only after your press ----
function addCode(c) {
  const guide = ['guide', 'steps', 'text'].includes(c.lang);
  const box = document.createElement('div');
  box.className = 'msg code' + (guide ? ' guide' : '');
  const head = document.createElement('div');
  head.className = 'codehead';
  const label = document.createElement('span');
  label.textContent = guide ? '' : (c.lang || 'code');
  const copy = document.createElement('button');
  copy.textContent = t('code.copy');
  copy.onclick = () => {
    navigator.clipboard?.writeText(c.text).then(() => { copy.textContent = t('code.copied'); setTimeout(() => { copy.textContent = t('code.copy'); }, 1500); }).catch(() => {});
  };
  const pre = document.createElement('pre');
  pre.textContent = c.text;
  head.append(label, copy);
  box.append(head, pre);
  el.log.append(box);
  el.log.scrollTop = el.log.scrollHeight;
}

function askRead(c) {
  const items = c.items.map(x => ({label: x.label, sub: x.where, run: () => readFile(x)}));
  if (items.length === 1) askChoice(t('read.ask').replace('{x}', items[0].label + ' (' + c.items[0].where + ')'), [{label: t('read.yes'), run: items[0].run}]);
  else askChoice(t('read.which'), items);
}

async function readFile(x) {
  try {
    const f = await (await api('/code/read', {token: x.token})).json();
    converse(t('read.msg').replace('{x}', f.name) + (f.truncated ? ' ' + t('read.cut') : '') + '\n```\n' + f.text + '\n```', null, null, '', '📄 ' + f.name);
  } catch (e) { addMessage('note', t('read.err').replace('{x}', x.label)); }
}

// ---- a chain of steps: you approve the whole plan once, then she gets the steps one by one; every step keeps its own plates ----
let plan = null, planTurn = false;   // the running plan; true while the runner itself is speaking to her
const PLAN_SECONDS = 600;
function askPlan(steps) {
  if (plan) return;
  askChoice(t('plan.ask').replace('{n}', steps.length) + ' ' + steps.map((s, i) => (i + 1) + ') ' + s).join(' · '), [{label: t('plan.yes'), run: () => runPlan(steps)}]);
}
function cancelPlan() { if (plan && !planTurn) plan.cancelled = true; }
function showPlanStop(on) { const b = document.getElementById('plan-stop'); if (b) b.hidden = !on; }
document.getElementById('plan-stop')?.addEventListener('click', () => {   // his Stop: the step in progress finishes, no next step starts
  if (plan) { plan.cancelled = true; showPlanStop(false); }
});
async function planIdle(p, limit) {
  const until = Date.now() + limit;
  await new Promise(r => setTimeout(r, 700));
  while (!p.cancelled && Date.now() < until && (busy || webPending || !el.confirm.hidden)) await new Promise(r => setTimeout(r, 400));
}
async function runPlan(steps) {
  if (plan) return;
  const p = plan = {cancelled: false, taint: false, started: Date.now()};
  showPlanStop(true);
  for (const [i, s] of steps.entries()) {
    await planIdle(p, 90000);
    if (p.cancelled || Date.now() - p.started > PLAN_SECONDS * 1000) { p.cancelled = true; break; }
    const at = {i: i + 1, n: steps.length, x: s};
    const fill = k => t(k).replace('{i}', at.i).replace('{n}', at.n).replace('{x}', at.x);
    addMessage('note', fill('plan.step'));
    if (p.taint) webRound = 1;   // text from the internet was read earlier in this plan: nothing opens on its own
    planTurn = true;
    try { await converse(fill('plan.msg') + (at.i === at.n ? ' ' + t('plan.last') : ''), null, null, '', '▶ ' + at.i + '/' + at.n + ' ' + s); }
    finally { planTurn = false; }
  }
  await planIdle(p, 90000);
  addMessage('note', t(p.cancelled ? 'plan.stopped' : 'plan.done'));
  plan = null;
  showPlanStop(false);
}

// ---- the clipboard: she asks, you press Show, the page reads it and the text goes to her as a message (data, not orders) ----
function askClip() {
  askChoice(t('clip.ask'), [{label: t('clip.yes'), run: async () => {
    try {
      const text = ((await navigator.clipboard.readText()) || '').trim();
      if (!text) { addMessage('note', t('clip.empty')); return; }
      converse(t('clip.msg') + '\n```\n' + text.slice(0, 8000) + '\n```', null, null, '', '📋 ' + t('clip.title'));
    } catch (e) { addMessage('note', t('clip.err')); }
  }}]);
}

// ---- audit of a whole project: she asks, you press Show, the program measures and the report goes to her ----
function askScan(s) {
  askChoice(t('scan.ask').replace('{x}', s.project + ' (' + s.where + ')'), [{label: t('scan.yes'), run: async () => {
    try {
      const r = await (await api('/code/scan', {token: s.token})).json();
      if (r.error) throw new Error(r.error);
      converse(t('scan.msg').replace('{x}', r.name) + '\n```\n' + r.text + '\n```', null, null, '', '🔎 ' + r.name);
    } catch (e) { addMessage('note', t('scan.err')); }
  }}]);
}

// ---- diagnostics of this computer: she asks, you press Show, read-only facts (ports, disk, tools) go to her ----
function askEnv(e) {
  askChoice(t('env.ask').replace('{x}', e.scope), [{label: t('env.yes'), run: async () => {
    try {
      const r = await (await api('/env/run', {token: e.token})).json();
      if (r.error) throw new Error(r.error);
      converse(t('env.msg') + '\n```\n' + r.text + '\n```', null, null, '', '🖥 ' + t('env.title'));
    } catch (err) { addMessage('note', t('env.err')); }
  }}]);
}

// ---- review of git changes: she asks, you press Show, read-only git runs and the program's report goes to her ----
function askDiff(d) {
  askChoice(t('diff.ask').replace('{x}', d.project).replace('{s}', d.scope), [{label: t('diff.yes'), run: async () => {
    try {
      const r = await (await api('/git/diff', {token: d.token})).json();
      if (r.error) { addMessage('note', t('diff.err.' + r.error)); return; }
      converse(t('diff.msg').replace('{x}', r.name) + '\n```diff\n' + r.text + '\n```', null, null, '', '🔀 ' + r.name);
    } catch (e) { addMessage('note', t('diff.err.failed')); }
  }}]);
}

// ---- a read-only query on a SQLite file of the project: she asks, you see the exact query and press Run ----
function sqlFail(code, names) {
  addMessage('note', t('sql.err.' + code).replace('{x}', (names || []).join(', ')));
}
function askSql(q) {
  askChoice(t('sql.ask').replace('{x}', q.db).replace('{q}', q.sql), [{label: t('sql.yes'), run: async () => {
    try {
      const r = await api('/sql/run', {token: q.token}).then(x => x.json(), () => ({error: 'failed'}));
      if (r.error) { addMessage('note', t('sql.err.' + (r.error === 'badquery' ? 'badquery' : r.error)).replace('{x}', r.detail || '')); return; }
      webRound = 2;   // values from a database are data: nothing she then proposes opens by itself
      converse(t('sql.msg').replace('{x}', r.db).replace('{n}', r.rows) + (r.cut ? ' ' + t('sql.cut') : '') + '\n```\n' + r.text + '\n```', null, null, '', '🗄 ' + r.db);
    } catch (e) { addMessage('note', t('sql.err.failed')); }
  }}]);
}

// ---- his documents and folders: she asks to read one (you press Show), or to tidy up (you press Move; the journal can undo it) ----
function askDocRead(c) {
  const ask = x => (x.dir ? t('doc.ask.dir') : t('doc.ask')).replace('{x}', x.label + ' (' + x.where + ')');
  const items = c.items.map(x => ({label: (x.dir ? '📁 ' : '📄 ') + x.label, sub: x.where, run: () => readDoc(x)}));
  if (items.length === 1) askChoice(ask(c.items[0]), [{label: t('read.yes'), run: items[0].run}]);
  else askChoice(t('read.which'), items);
}

async function readDoc(x) {
  try {
    const f = await (await api('/doc/read', {token: x.token})).json();
    if (f.error) throw Error(f.error);
    webRound = 2;   // a document may carry someone else's words: nothing she then proposes opens by itself
    converse(t(f.dir ? 'doc.msg.dir' : 'doc.msg').replace('{x}', f.name) + (f.truncated ? ' ' + t('read.cut') : '') + '\n<<<\n' + f.text + '\n>>>', null, null, '', (f.dir ? '📁 ' : '📄 ') + f.name);
  } catch (e) { addMessage('note', t('doc.err').replace('{x}', x.label)); }
}

function askMove(p) {
  askChoice(t('move.ask').replace('{x}', p.label).replace('{a}', p.where).replace('{b}', p.to), [{label: t('move.yes'), run: async () => {
    try {
      const r = await api('/doc/move', {token: p.token});
      addMessage('note', t('move.done').replace('{x}', p.label));
      converse(t('move.msg').replace('{x}', p.label).replace('{b}', p.to), null, null, '', '📦 ' + p.label);
    } catch (e) { addMessage('note', t('move.err').replace('{x}', p.label)); }
  }}]);
}

// ---- the internet: she looked something up herself; the excerpts go back to her as data, never as orders ----
let webRound = 0, webPending = null, webQuery = '';
function researched(w) { webPending = w; }   // she is still speaking: the excerpts go back to her when this turn ends
function followWeb(w) {
  if (w.calc) {   // the program's own arithmetic: not from the internet, so no caution about commands inside
    addMessage('note', t('calc.done').replace('{x}', w.text));
    webRound = w.depth; webQuery = '';
    converse(t('calc.msg').replace('{x}', w.text), null, null, '', '🧮 ' + w.text);
    return;
  }
  if (plan) plan.taint = true;
  addMessage('note', t('web.done').replace('{x}', w.query));
  webRound = w.depth; webQuery = w.query;
  converse(t('web.msg').replace('{x}', w.query) + '\n<<<\n' + w.text + '\n>>>', null, null, '', '🌐 ' + w.query);
}

// ---- commands: she proposes a build / test / script command; you see it and the folder, press Run, and the output goes back to her ----
let codeLoop = null;   // a command that failed and is being fixed: how many rounds so far
function askRun(p) {
  askChoice(t('run.ask').replace('{c}', p.cmd).replace('{x}', p.where), [{label: t('run.yes'), run: async () => {
    setStatus(t('run.busy'));
    try {
      const r = await (await api('/run/go', {token: p.token})).json();
      setStatus('');
      codeLoop = r.ok ? null : {n: (codeLoop?.n || 0) + 1};
      converse(t('run.msg').replace('{c}', r.cmd).replace('{x}', r.error === 'timeout' ? t('run.timeout') : r.code === null ? t('run.failed') : t('run.code').replace('{n}', r.code)) + '\n```\n' + (r.text || t('run.empty')) + '\n```', null, null, '', '▶ ' + r.cmd);
    } catch (e) { setStatus(''); addMessage('note', t('run.err').replace('{c}', p.cmd)); }
  }}]);
}

// ---- fixing code in rounds: after you applied her fix the same command is offered again (you press each time), at most 5 rounds ----
function offerRerun() {
  if (codeLoop.n >= 5) { codeLoop = null; addMessage('note', t('loop.limit')); return; }
  askChoice(t('loop.ask'), [{label: t('run.yes'), run: async () => {
    setStatus(t('run.busy'));
    try {
      const r = await (await api('/run/again', {})).json();
      setStatus('');
      if (r.error && !r.cmd) throw Error(r.error);
      codeLoop = r.ok ? null : {n: (codeLoop?.n || 0) + 1};
      converse(t('run.msg').replace('{c}', r.cmd).replace('{x}', r.error === 'timeout' ? t('run.timeout') : r.code === null ? t('run.failed') : t('run.code').replace('{n}', r.code)) + '\n```\n' + (r.text || t('run.empty')) + '\n```', null, null, '', '▶ ' + r.cmd);
    } catch (e) { setStatus(''); codeLoop = null; addMessage('note', t('loop.err')); }
  }}]);
}

// ---- code edits: she proposes exact replacements in a file you showed her; you see the diff and press Apply ----
function askEdit(d, project) {
  const box = $('#diffbox'), pre = $('#diff-text');
  $('#diff-title').textContent = t(project ? (d.inplace ? 'project.addtitle' : 'project.title') : 'edit.title').replace('{x}', d.file);
  $('#diff-stat').textContent = (project ? t(d.inplace ? 'project.stat.ws' : 'project.stat').replace('{n}', d.files.length).replace('{a}', d.added) : t('edit.stat').replace('{a}', d.added).replace('{r}', d.removed)) + (d.cut ? ' ' + t('edit.cut') : '');
  pre.replaceChildren();
  for (const line of d.diff.split('\n')) {
    if (line.startsWith('---') || line.startsWith('+++')) continue;
    const row = document.createElement('span');
    row.className = line.startsWith('@@') ? 'hunk' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : '';
    row.textContent = line + '\n';
    pre.append(row);
  }
  const close = () => { box.hidden = true; };
  $('#diff-apply').textContent = t('edit.apply');
  $('#diff-no').textContent = t('act.no');
  $('#diff-no').onclick = close;
  $('#diff-apply').onclick = async () => {
    close();
    try {
      const r = await (await api(project ? '/project/make' : '/code/edit', {token: d.token})).json();
      addMessage('note', t(project ? 'project.done' : 'edit.done').replace('{x}', r.name).replace('{n}', r.count));
      if (codeLoop && !project) offerRerun();
    } catch (e) { addMessage('note', e.message); }
  };
  box.hidden = false;
}

// ---- documents: she writes Word / PowerPoint / Excel only after your press, into one folder ----
function askDocument(d) {
  const size = t('doc.size.' + d.kind).replace('{n}', d.size);
  const make = open => async () => {
    try {
      const r = await (await api('/doc/make', {token: d.token, open})).json();
      addMessage('note', t(r.opened ? 'doc.done.open' : 'doc.done').replace('{x}', r.name));
    } catch (e) { addMessage('note', e.message); }
  };
  askChoice(t('doc.ask').replace('{app}', d.app).replace('{x}', d.title).replace('{n}', size),
    [{label: t('doc.make.open'), run: make(true)}, {label: t('doc.make'), run: make(false)}]);
}

// ---- Unreal Engine: one fixed operation per plate, run by the server through Unreal's Python remote execution ----
function askUnreal(u) {
  const text = t(u.risky ? 'unreal.risky' : 'unreal.ask').replace('{x}', u.text);
  askChoice(text, [{label: t('unreal.go'), run: async () => {
    try {
      const r = await (await api('/unreal/run', {token: u.token})).json();
      addMessage('note', r.ok ? t('unreal.done').replace('{x}', u.text) : t('unreal.err.' + r.error));
    } catch (e) { addMessage('note', t('unreal.err.failed') + ' (' + e.message + ')'); }
  }}]);
}

// ---- Godot: one fixed operation per plate, run by the server on the project folder ----
function askGodot(g) {
  const text = t(g.risky ? 'godot.risky' : 'godot.ask').replace('{x}', g.text).replace('{p}', g.project);
  askChoice(text, [{label: t('godot.go'), run: async () => {
    try {
      const r = await (await api('/godot/run', {token: g.token})).json();
      addMessage('note', r.ok ? t('godot.done').replace('{x}', g.text) : t('godot.err.' + r.error));
    } catch (e) { addMessage('note', t('godot.err.failed') + ' (' + e.message + ')'); }
  }}]);
}

// ---- Unity: one fixed operation per plate, run on the project by the server ----
function askUnity(g) {
  const text = t(g.risky ? 'unity.risky' : 'unity.ask').replace('{x}', g.text).replace('{p}', g.project);
  askChoice(text, [{label: t('unity.go'), run: async () => {
    try {
      const r = await (await api('/unity/run', {token: g.token})).json();
      addMessage('note', r.ok ? t('unity.done').replace('{x}', g.text) : t('unity.err.' + r.error));
    } catch (e) { addMessage('note', t('unity.err.failed') + ' (' + e.message + ')'); }
  }}]);
}

// ---- mouse and keyboard task: she looks at the screen, proposes one action at a time, the server limits and runs it ----
let agentRun = null;   // {stop} while a task is running
const sleep = ms => new Promise(r => setTimeout(r, ms));

function askTask(task) {
  if (!DESKTOP) return;
  askChoice(t('task.ask').replace('{x}', task.text), [{label: t('task.start'), run: () => runTask(task)}]);
}

function stopTask() {
  if (!agentRun) return;
  agentRun.stop = true;
  api('/agent/stop', {}).catch(() => {});
}

async function runTask(task) {
  if (agentRun) return;
  const run = agentRun = {stop: false};
  const hud = $('#hud'), hudText = $('#hud-text'), steps = [];
  hud.hidden = false;
  let outcome = null, spoken = '';
  try {
    await api('/agent/start', {token: task.token});
    for (let i = 0; i < 30 && !run.stop; i++) {
      lastActivity = Date.now();
      hudText.textContent = t('task.look');
      document.body.classList.add('shooting');   // she does not photograph herself, the panel or the stop button
      await sleep(160);
      let shot;
      try { shot = await window.desktop.capture(true); } finally { document.body.classList.remove('shooting'); }
      if (!shot) throw Error(t('task.err'));
      if (run.stop) break;
      const r = await (await api('/agent/step', {image: shot.image, steps, lang: uiLang})).json();
      if (run.stop) break;
      const a = r.action;
      hudText.textContent = r.thought || a.action;
      if (a.action === 'done' || a.action === 'fail') {
        await api('/agent/do', {action: a});
        outcome = a.action === 'done' ? t('task.done') : t('task.failed');
        spoken = r.say;
        break;
      }
      if (a.risky) {   // sending, paying, deleting: the creator says yes each time
        const ok = await new Promise(res => askChoice(t('task.risky').replace('{x}', r.thought || a.action), [{label: t('act.yes'), run: () => res(true)}], () => res(false)));
        if (!ok || run.stop) { stopTask(); break; }
      }
      await api('/agent/do', {action: a});
      steps.push(r.thought || a.action);
      await sleep(900);   // the program needs a moment to react before the next look
    }
    if (!outcome) outcome = run.stop ? t('task.stopped') : t('task.budget');
  } catch (e) {
    outcome = e.message === 'moved' ? t('task.moved') : e.message === 'budget' ? t('task.budget') : t('task.err') + ' ' + e.message;
  } finally {
    hud.hidden = true;
    agentRun = null;
    api('/agent/stop', {}).catch(() => {});
    lastActivity = Date.now();
  }
  addMessage('note', outcome);
  if (spoken) { addMessage('bot', spoken); if (el.speak.checked) await speak(spoken, []).catch(() => {}); }
}
$('#hud-stop').addEventListener('click', stopTask);
if (DESKTOP) window.desktop.onStopAgent?.(stopTask);   // Ctrl+Alt+K from anywhere

// ---- chat ----
function addMessage(kind, text) {
  const box = document.createElement('div');
  box.className = 'msg ' + kind;
  box.textContent = text;
  el.log.append(box);
  el.log.scrollTop = el.log.scrollHeight;
  return box;
}

let busy = false;
function setBusy(on) { busy = on; el.send.disabled = el.message.disabled = on; }

let mediaNow = '';   // title of the media window right now ('' when none or the setting is off)
const looksMedia = s => /YouTube|Twitch|Crunchyroll|Netflix|Disney\+|Okko|ivi|Кинопоиск|смотреть|VLC|MPC|mpv|PotPlayer|Spotify|Музыка|Music|SoundCloud|AniLibria|Shikimori|HiAnime|AIMP|foobar|Wink|Amediateka|Prime Video/i.test(s || '');
let lastActivity = Date.now(), unanswered = 0;   // initiative: how long it has been quiet, how many of her lines got no reply

/* The server streams the reply sentence by sentence (one JSON object per line). */
async function* readEvents(resp) {
  const reader = resp.body.getReader(), decoder = new TextDecoder();
  let rest = '';
  for (;;) {
    const {done, value} = await reader.read();
    rest += decoder.decode(value || new Uint8Array(), {stream: !done});
    const lines = rest.split('\n');
    rest = lines.pop();
    for (const line of lines) if (line.trim()) yield JSON.parse(line);
    if (done) break;
  }
  if (rest.trim()) yield JSON.parse(rest);
}

let turn = null;   // the reply being spoken right now: {abort, cancelled}
let lastCut = null;   // the sentence she was saying when she was cut off: {text, at}
/* Cut her off mid-sentence: stop the voice and the incoming reply. */
function interrupt() {
  if (turn && !turn.cancelled && el.subtitle.classList.contains('show') && el.subtitle.textContent) lastCut = {text: el.subtitle.textContent, at: Date.now()};
  if (turn) { turn.cancelled = true; turn.abort.abort(); }
  stopSpeaking();
}

/* Speak one sentence: voice if it could be synthesized, otherwise act it out silently. */
async function playChunk(text, cues, audio, mine) {
  const url = await audio;
  if (mine.cancelled) { if (url) URL.revokeObjectURL(url); return; }
  el.subtitle.textContent = text;
  el.subtitle.classList.add('show');
  setStatus('');
  if (url) {
    try { await playSpeech(url, text, cues); return; } catch (e) {
      if (!mine.cancelled) {
        if (e.name === 'NotAllowedError') setStatus(t('err.autoplay'));
        else setStatus(e.message, true);
      }
    }
  }
  if (!mine.cancelled) await new Promise(r => setTimeout(r, performSilently(text, cues) * 1000));
}

/* initiative = 'greet' | 'idle': she speaks first, no user message is sent. */
// Words that mean "look at my screen" (the explicit non-letter guards are there because word boundaries ignore Cyrillic).
const SCREEN_ASK = /(^|[^а-яё])(видишь|видела|смотри|посмотри|глянь|взгляни|оцени)([^а-яё]|$)|экран(а|е|у|ом|ы)?([^а-яё]|$)|вот (это|так|тут)|что я (сейчас )?делаю|как тебе (это|вот)|что (ты )?(думаешь|скажешь) (об?|про) (этом|этой|этих)|can you see|do you see|look at (my|this|the) (screen|this)|my screen|what am i (doing|looking at)|what do you think (of|about) (this|that)|화면|보이니|봐 ?줘|見える|画面|見て/i;
let lastGlanceAt = 0;
let screenTalkUntil = 0;   // while the talk is about the screen, every message of yours comes with a fresh screenshot
let spokenNext = false, voiceStyle = '';   // voiceStyle: how it was said (quieter, slower than usual), from the local recognizer   // the next message was dictated through the microphone: the server is told, because recognition can mishear
async function converse(text, initiative = null, image = null, windowTitle = '', shownText = null) {
  if (busy || (!initiative && !text.trim())) return;
  if (!initiative) cancelPlan();   // you spoke yourself: the plan stops
  if (window.STREAMING && ['screen', 'media', 'care', 'late', 'scene', 'return', 'remind'].includes(initiative)) return;   // nothing private on the stream
  if (!(el.bargein.checked && el.handsfree.checked)) stopRecognition(true);
  stopSpeaking();
  const bubble = initiative ? null : addMessage('user', shownText ?? text);
  if (initiative && !image && !window.STREAMING) unanswered++; else if (!initiative) unanswered = 0;   // a glance at the screen is not her pestering you
  setBusy(true);
  avatar.thinking = true;
  avatar.perform('look:user');   // acknowledge the message before she starts thinking
  setStatus(initiative ? '' : t('thinking'));
  const mine = turn = {abort: new AbortController(), cancelled: false};
  let box = null, shown = '', playing = Promise.resolve(), voiceEmotion = 'neutral';
  try {
    const camera = !!(vision && vision.active);
    const extra = {camera, media: mediaNow, hear: !!($('#hear') && $('#hear').checked), songid: !!($('#songid') && $('#songid').checked), scene: el.bg.value, presence: el.presence.checked, lang: uiLang, agent: el.agent.checked, control: DESKTOP && el.control.checked, work: el.work.checked, fx: avatar.availableFx(), mo: avatar.availableMotions()};
    if (windowTitle) extra.window = windowTitle;
    if (spokenNext && !initiative) { extra.spoken = true; if (voiceStyle) extra.voice = voiceStyle; }
    spokenNext = false; voiceStyle = '';
    if (!initiative && lastCut && Date.now() - lastCut.at < 30000) extra.cut = lastCut.text;
    lastCut = null;
    if (webRound) { extra.web = true; extra.depth = webRound; extra.webq = webQuery; webRound = 0; }
    const aboutScreen = !initiative && !window.STREAMING && DESKTOP && (SCREEN_ASK.test(text) || (el.eye.checked && Date.now() < screenTalkUntil));
    if (aboutScreen) {   // "видишь?", "посмотри" (and the follow-ups, "а сейчас?"): look right now, if she is allowed to
      if (!el.eye.checked) extra.screen_off = 'off';
      else {
        setStatus(t('look.screen'));
        const shot = await window.desktop.capture().catch(() => null);
        if (shot) { image = shot.image; extra.window = shot.title; lastGlanceAt = Date.now(); screenTalkUntil = Date.now() + 180000; }
        else extra.screen_off = 'failed';
      }
    } else if (!initiative && !DESKTOP && SCREEN_ASK.test(text)) extra.screen_off = 'unavailable';
    if (image) extra.image = image;
    const resp = await api('/chat', initiative ? {initiative, ...extra} : {message: text, ...extra}, mine.abort.signal);
    if (!initiative) el.message.value = '';
    for await (const ev of readEvents(resp)) {
      if (mine.cancelled) break;
      if (ev.error) throw Error(fixErr(ev.error));
      if (ev.action) { askAction(ev.action); continue; }
      if (ev.opened) { addMessage('note', t('act.done').replace('{x}', ev.opened)); continue; }
      if (ev.openfail) { addMessage('note', t('act.fail').replace('{x}', ev.openfail)); continue; }
      if (ev.web) { researched(ev.web); continue; }
      if (ev.calc) { researched(Object.assign({calc: true}, ev.calc)); continue; }
      if (ev.calcfail) { addMessage('note', t('calc.none').replace('{x}', ev.calcfail)); continue; }
      if (ev.webfail) { addMessage('note', t('web.none').replace('{x}', ev.webfail)); continue; }
      if (ev.task) { askTask(ev.task); continue; }
      if (ev.unreal) { askUnreal(ev.unreal); continue; }
      if (ev.godot) { askGodot(ev.godot); continue; }
      if (ev.unity) { askUnity(ev.unity); continue; }
      if (ev.unityfail) { addMessage('note', t('unity.err.' + ev.unityfail)); continue; }
      if (ev.godotfail) { addMessage('note', t('godot.err.' + ev.godotfail)); continue; }
      if (ev.readfile) { askRead(ev.readfile); continue; }
      if (ev.clip) { askClip(); continue; }
      if (ev.noted) { addMessage('note', t(ev.noted.added ? 'nook.added' : 'nook.saved').replace('{x}', ev.noted.title)); continue; }
      if (ev.notefail) { addMessage('note', t('nook.fail.' + ({secret: 'secret', full: 'full'}[ev.notefail] || 'other'))); continue; }
      if (ev.plan) { askPlan(ev.plan.steps); continue; }
      if (ev.scan) { askScan(ev.scan); continue; }
      if (ev.env) { askEnv(ev.env); continue; }
      if (ev.diff) { askDiff(ev.diff); continue; }
      if (ev.difffail) { addMessage('note', t('diff.err.' + ev.difffail)); continue; }
      if (ev.sql) { askSql(ev.sql); continue; }
      if (ev.sqlfail) { sqlFail(ev.sqlfail.fail, ev.sqlfail.names); continue; }
      if (ev.scanfail) { addMessage('note', t('scan.err.' + ev.scanfail)); continue; }
      if (ev.docfile) { askDocRead(ev.docfile); continue; }
      if (ev.move) { askMove(ev.move); continue; }
      if (ev.movefail) { addMessage('note', t('move.bad.' + ev.movefail)); continue; }
      if (ev.run) { askRun(ev.run); continue; }
      if (ev.runfail) { addMessage('note', t('run.bad.' + ev.runfail)); continue; }
      if (ev.standup) { addMessage('note', t('standup.saved')); continue; }
      if (ev.document) { askDocument(ev.document); continue; }
      if (ev.edit) { askEdit(ev.edit); continue; }
      if (ev.perform) { const p = ev.perform; playing = playing.then(() => performSong(p, mine)); continue; }
      if (ev.project) { askEdit(ev.project, true); continue; }
      if (ev.projectfail) { addMessage('note', t('project.err.' + ev.projectfail)); continue; }
      if (ev.editfail) { addMessage('note', t('edit.err.' + ev.editfail)); continue; }
      if (ev.docfail) { addMessage('note', t('doc.bad')); continue; }
      if (ev.code) { addCode(ev.code); box = null; shown = ''; continue; }
      if (ev.choices) { askFound(ev.choices); continue; }
      if (ev.notfound) { addMessage('note', t('act.nf').replace('{x}', ev.notfound)); continue; }
      if (ev.done) { if (ev.mood) avatar.mood = ev.mood; if (ev.quiet && image) screenQuietAt = Date.now(); continue; }
      clearTimeout(emotionTimer);
      box = box || addMessage('bot', '');
      shown += (shown ? ' ' : '') + ev.answer;
      box.textContent = shown;
      el.log.scrollTop = el.log.scrollHeight;
      // synthesize right away (the next sentence is prepared while the current one plays), play in order
      const emotion = (ev.script.match(/\[(\w+)\]/g) || []).map(x => x.slice(1, -1)).find(x => EMOTION_PARAMS[x]);
      if (emotion) voiceEmotion = emotion;   // the mood colours the intonation of this and the next lines
      const audio = el.speak.checked ? fetchSpeech(ev.answer, voiceEmotion).catch(err => { setStatus(err.message, true); return null; })
                                     : Promise.resolve(null);
      const cues = parseScript(ev.script);
      playing = playing.then(() => playChunk(ev.answer, cues, audio, mine));
    }
    await playing;
    if (image && initiative === 'screen' && box) screenTalkUntil = Date.now() + 180000;   // she commented: your reply is probably about it
    emotionTimer = setTimeout(() => avatar.setEmotion('neutral'), 2500);   // the face relaxes after the last line
  } catch (e) {
    if (mine.cancelled) { /* interrupted on purpose */ }
    else {
      if (!box) bubble?.remove();
      if (!initiative) setStatus(e instanceof TypeError ? t('err.noconn') : e.message, true);
    }
  } finally {
    if (turn === mine) turn = null;
    lastActivity = Date.now();
    avatar.thinking = false;
    setBusy(false);
    el.subtitle.classList.remove('show');
    const w = webPending; webPending = null;
    if (w && !mine.cancelled) followWeb(w);
    else if (el.handsfree.checked) startRecognition();
  }
}

// Luna speaks up on her own after a quiet spell (but not while you type or talk, and never more than twice in a row).
// Presence mode ("like a person in the room"): she speaks up more often, but each unanswered line makes her wait longer,
// and sometimes she just stays quiet, as people do.
const nextIdle = () => el.presence.checked ? 10000 + Math.random() * 25000 : 90000 + Math.random() * 90000;
let idleLimit = nextIdle();
setInterval(() => {
  if (window.STREAMING) return;   // on the stream the dead air is handled by stream.js
  if (!el.initiative.checked || busy || agentRun || document.hidden || avatar.listening || el.message.value || !avatar.model) return;
  if (vision && vision.active && !vision.present) return;   // she can see nobody is there: no point talking
  const presence = el.presence.checked;
  // Presence: she never goes fully quiet, but each unanswered line stretches the pause (up to about 4 minutes).
  const wait = presence ? Math.min(idleLimit * (1 + unanswered * 1.2), 240000) : idleLimit;
  if ((!presence && unanswered >= 2) || Date.now() - lastActivity < wait) return;
  idleLimit = nextIdle();
  if (presence && Math.random() < 0.15) {   // comfortable silence, but not a frozen doll: a small silent gesture
    avatar.perform(['tilt', 'sigh', 'look:up', 'look:away', 'lean', 'shrug', 'giggle'][Math.floor(Math.random() * 7)]);
    return;
  }
  const hour = new Date().getHours();
  if (hour < 5 && !lateDone) { lateDone = true; converse('', 'late'); }   // once per launch: it is the middle of the night
  else converse('', 'idle');
}, 10000);
let lateDone = false;
// She wakes for a date she remembers (an exam today): from the tray too. The server says when it is time (and not at night).
setInterval(async () => {
  if (!el.initiative.checked || busy || agentRun || avatar.listening || !avatar.model || !provReady()) return;
  try { if (!(await (await api('/care/due', {})).json()).due) return; } catch { return; }
  if (DESKTOP) window.desktop.wake?.();
  converse('', 'care');
}, 120000);
// A reminder he set: when its time comes she speaks first (the page must be open, the tray keeps it so).
setInterval(async () => {
  if (busy || agentRun || avatar.listening || !avatar.model || !provReady()) return;
  try { if (!(await (await api('/reminder/due', {})).json()).due) return; } catch { return; }
  if (DESKTOP) window.desktop.wake?.();
  converse('', 'remind');
}, 15000);
for (const ev of ['input', 'focus']) el.message.addEventListener(ev, () => { lastActivity = Date.now(); });

el.form.addEventListener('submit', e => { e.preventDefault(); ensureAudio(); converse(el.message.value); });
el.message.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); el.form.requestSubmit(); }
});
$('#reset').addEventListener('click', async () => {
  try { await api('/reset', {}); el.log.replaceChildren(); stopSpeaking(); avatar.setEmotion('neutral'); setStatus(t('hist.cleared')); }
  catch (e) { setStatus(e.message, true); }
});

$('#forget').addEventListener('click', async () => {
  if (!confirm(t('forget.confirm'))) return;
  try { await api('/forget', {}); el.log.replaceChildren(); stopSpeaking(); avatar.setEmotion('neutral'); setStatus(t('mem.cleared')); }
  catch (e) { setStatus(e.message, true); }
});

// ---- microphone (browser speech recognition) ----
/* Inside Electron the browser's speech engine does not work ("network" error): the server listens to the microphone and
   recognizes it on this computer. This class offers the same few members the code below uses. */
class LocalRecognition {
  constructor() { this.lang = 'ru-RU'; this.stopped = false; }
  async start() {
    try {
      while (!this.stopped) {
        this.poll = setInterval(async () => {   // the words appear while you are still speaking
          try {
            const p = await (await api('/listen', {partial: true})).json();
            if (!this.stopped && p.level && this.onlevel) this.onlevel(p.level);
            if (!this.stopped && p.text && this.onresult) this.onresult({resultIndex: 0, results: [Object.assign([{transcript: p.text}], {isFinal: false})]});
          } catch { /* the next tick tries again */ }
        }, 300);
        const r = await (await api('/listen', {lang: this.lang})).json().finally(() => clearInterval(this.poll));
        if (this.stopped) return;
        if (r.status === 'loading') { setStatus(t('mic.loading')); await new Promise(ok => setTimeout(ok, 2000)); continue; }
        if (r.status === 'error') return this.fail('local:' + (r.error || ''));
        const text = (r.text || '').trim();
        voiceStyle = text ? (r.style || '') : '';
        if (text && this.onresult) this.onresult({resultIndex: 0, results: [Object.assign([{transcript: text}], {isFinal: true})]});
        else if (!text && !r.cancelled && this.onerror) this.onerror({error: 'no-speech'});
        break;
      }
    } catch (err) {
      if (!this.stopped) this.fail(err.message === 'missing' ? 'missing' : err.message === 'lang' ? 'lang' : 'local:' + err.message);
      return;
    }
    if (!this.stopped && this.onend) this.onend();
  }
  fail(code) { this.stopped = true; clearInterval(this.poll); if (this.onerror) this.onerror({error: code}); if (this.onend) this.onend(); }
  stop() { this.stopped = true; clearInterval(this.poll); api('/listen', {cancel: true}).catch(() => {}); }
}
const SR = DESKTOP ? LocalRecognition : (window.SpeechRecognition || window.webkitSpeechRecognition);
let recognition = null, wantListening = false;
/* The speech model takes a while to load (half a minute on a slow computer): load it ahead of the first press of the microphone. */
function warmRecognizer() { if (DESKTOP) api('/listen', {lang: el.lang.value, warm: true}).catch(() => {}); }
el.lang.addEventListener('change', warmRecognizer);
/* Microphone test: a level meter and what she heard, so a silent or very quiet input is told apart from a recognition problem. */
$('#mic-test').addEventListener('click', () => {
  const btn = $('#mic-test'), meter = $('#mic-meter'), verdict = $('#mic-verdict');
  if (!SR) { setStatus(t('mic.unsupported'), true); return; }
  if (btn.disabled) return;
  if (recognition) stopRecognition();
  btn.disabled = true; verdict.hidden = false; meter.hidden = !DESKTOP; verdict.textContent = t('mic.t.say');
  let peak = 0, heard = '', error = '';
  const rec = new SR();
  rec.lang = el.lang.value; rec.interimResults = true; rec.continuous = false;
  rec.onlevel = lv => { peak = Math.max(peak, lv.peak); meter.firstElementChild.style.width = Math.min(100, Math.round(lv.peak * 300)) + '%'; };
  rec.onresult = e => { heard = e.results[0][0].transcript; verdict.textContent = heard; };
  rec.onerror = e => { error = e.error; };
  rec.onend = () => {
    btn.disabled = false; meter.firstElementChild.style.width = '0';
    if (error && error !== 'no-speech') verdict.textContent = error === 'not-allowed' ? t('mic.denied') : error === 'missing' ? t('mic.missing') : t('mic.error') + error.replace(/^local:/, '');
    else if (heard) verdict.textContent = t('mic.t.ok') + heard + (DESKTOP && peak < 0.02 ? ' ' + t('mic.t.low') : '');
    else verdict.textContent = DESKTOP && peak < 0.003 ? t('mic.t.quiet') : t('mic.t.words');
  };
  try { rec.start(); } catch { rec.onend(); }
});

function setMic(on) { el.mic.setAttribute('aria-pressed', String(on)); avatar.listening = on; }

function stopRecognition(keepFlag) {
  if (!keepFlag) wantListening = false;
  if (recognition) { recognition.onend = null; try { recognition.stop(); } catch { /* already stopped */ } recognition = null; }
  setMic(false);
}

function startRecognition() {
  if (!SR) { setStatus(t('mic.unsupported'), true); return; }
  if (recognition || busy) return;
  wantListening = true;
  ensureAudio();
  recognition = new SR();
  recognition.lang = el.lang.value;
  recognition.interimResults = true;
  recognition.continuous = false;
  let finalText = '';
  recognition.onresult = e => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalText += e.results[i][0].transcript; else interim += e.results[i][0].transcript;
    }
    el.message.value = finalText + interim;
    if (busy && el.bargein.checked && (finalText + interim).trim().length >= 3) interrupt();   // you started talking: she stops
    reactToWords(finalText + interim);
  };
  recognition.onerror = e => {
    if (e.error === 'no-speech' || e.error === 'aborted') return;
    wantListening = false;
    setStatus(e.error === 'not-allowed' ? t('mic.denied') : e.error === 'missing' ? t('mic.missing') : e.error === 'lang' ? t('mic.lang')
      : t('mic.error') + e.error.replace(/^local:/, ''), true);
  };
  recognition.onend = () => {
    recognition = null;
    setMic(false);
    if (finalText.trim()) { wantListening = el.handsfree.checked; whenIdle().then(() => { spokenNext = true; return converse(finalText.trim()); }); }
    else if (wantListening && el.handsfree.checked) startRecognition();
  };
  recognition.start();
  setMic(true);
  setStatus(t('listening'));
}

/* Resolves once the previous reply has been cleaned up (an interrupted one finishes within moments). */
async function whenIdle() {
  for (let i = 0; i < 30 && busy; i++) await new Promise(r => setTimeout(r, 100));
}

// While you talk she reacts to what she hears: a smile at warm words, a sad face at heavy ones.
const POSITIVE = /спасибо|класс|круто|супер|люблю|рад[аы]?(?![а-я])|ура\b|здорово|отлично|прекрасн|мило|thanks|thank you|great|love|awesome|nice|happy|ありがとう|嬉しい|好き|最高|감사|좋아|사랑/i;
const NEGATIVE = /груст|плохо|печаль|умер|устал|обидно|ненавижу|злюсь|боюсь|тяжело|sad\b|tired|hate|angry|terrible|悲しい|疲れた|嫌い|つらい|슬퍼|피곤|싫어/i;
let reactTimer = null, lastReact = 0;
function reactToWords(heard) {
  if (busy || Date.now() - lastReact < 2500) return;
  const emotion = NEGATIVE.test(heard) ? 'sad' : POSITIVE.test(heard) ? 'happy' : null;
  if (!emotion) return;
  lastReact = Date.now();
  avatar.setEmotion(emotion);
  clearTimeout(reactTimer);
  reactTimer = setTimeout(() => avatar.setEmotion('neutral'), 3500);
}

// ---- camera (off at every start; the video never leaves the browser) ----
let vision = null;
function glance(emotion, ms) {
  if (busy || avatar.listening) return;
  avatar.setEmotion(emotion);
  clearTimeout(reactTimer);
  reactTimer = setTimeout(() => avatar.setEmotion('neutral'), ms);
}
const camNote = $('#camera-note');
function cameraNote(text, error = false) { camNote.textContent = text; camNote.className = 'hint' + (error ? ' error' : ''); setStatus(text, error); }
el.camera.addEventListener('change', async () => {
  if (!el.camera.checked) { vision?.stop(); vision = null; el.cam.hidden = true; cameraNote(''); return; }
  if (!confirm(t('cam.title') + '\n\n' + t('cam.confirm'))) { el.camera.checked = false; return; }
  cameraNote(t('cam.starting'));
  const v = new Vision(avatar, $('#cam-video'), {
    onSmile: () => glance('happy', 3000),
    onSurprise: () => glance('surprised', 2000),
    onReturn: () => { if (el.initiative.checked && !busy && avatar.model) converse('', 'return'); }});
  try {
    await v.start();
    if (!el.camera.checked) { v.stop(); return; }   // switched off while loading
    vision = v;
    el.cam.hidden = false;
    cameraNote(t('cam.on'));
  } catch (e) {
    v.stop();
    el.camera.checked = false;
    cameraNote(t('cam.' + e.name) !== 'cam.' + e.name ? t('cam.' + e.name) : e.message || t('cam.fail'), true);
  }
});

// Clicking Luna or pressing Escape while she talks cuts her off.
$('#stage').addEventListener('click', () => { if (busy || performing) interrupt(); });
addEventListener('keydown', e => { if (e.key === 'Escape' && (busy || performing)) interrupt(); });

// When you start typing she glances at the text box.
let lastGlance = 0;
el.message.addEventListener('input', () => {
  if (busy || Date.now() - lastGlance < 8000) return;
  lastGlance = Date.now();
  avatar.perform('look:down');
});

el.mic.addEventListener('click', () => {
  if (recognition) { stopRecognition(); setStatus(''); } else startRecognition();
});
el.handsfree.addEventListener('change', () => {
  persist();
  if (el.handsfree.checked) startRecognition(); else stopRecognition();
});

// ---- chat window: drag, minimize, close, tabs ----
/* One place for everything: the corner of the round button. The opened chat (conversation or settings, whatever their height) hangs from
   the same bottom-right corner and grows up and to the left, so the button never moves when the tab or the size changes. Dragging the
   button, or the opened chat by its header, moves that corner. anchor = distances from the right and bottom edges of the screen. */
let anchor = saved.anchor || (saved.iconPos ? {r: innerWidth - saved.iconPos.x - 92, b: innerHeight - saved.iconPos.y - 92} : saved.minimized && saved.pos ? {r: innerWidth - saved.pos.x - 92, b: innerHeight - saved.pos.y - 92} : null);
const folded = () => el.panel.classList.contains('minimized');
function applyPos() {
  if (!anchor) { Object.assign(el.panel.style, {left: '', top: '', right: '', bottom: '', maxHeight: ''}); return; }   // default corner
  const r = Math.min(Math.max(0, anchor.r), Math.max(0, innerWidth - 92)), b = Math.min(Math.max(0, anchor.b), Math.max(0, innerHeight - 92));
  Object.assign(el.panel.style, {left: 'auto', top: 'auto', right: r + 'px', bottom: b + 'px', maxHeight: folded() ? '' : Math.max(200, innerHeight - b - 8) + 'px'});
}
function setMinimized(on) {
  const P = el.panel;
  if (!anchor) anchor = {r: Math.max(0, innerWidth - (P.offsetLeft + P.offsetWidth)), b: Math.max(0, innerHeight - (P.offsetTop + P.offsetHeight))};   // the default corner becomes the anchor
  P.classList.toggle('minimized', on);
  applyPos();
}
el.head.addEventListener('pointerdown', e => {
  if (e.target.closest('button')) return;
  const r = el.panel.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
  const startX = e.clientX, startY = e.clientY;
  el.head.setPointerCapture(e.pointerId);
  const move = ev => { anchor = {r: innerWidth - (ev.clientX - dx + r.width), b: innerHeight - (ev.clientY - dy + r.height)}; applyPos(); };
  const up = ev => {
    el.head.removeEventListener('pointermove', move); el.head.removeEventListener('pointerup', up);
    if (el.panel.classList.contains('minimized') && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 5) setMinimized(false);   // a click on the picture opens the chat
    persist();
  };
  el.head.addEventListener('pointermove', move);
  el.head.addEventListener('pointerup', up);
});
$('#min').addEventListener('click', () => { setMinimized(!el.panel.classList.contains('minimized')); persist(); });
$('#close').addEventListener('click', () => { el.panel.hidden = true; el.openChat.hidden = false; persist(); });
el.openChat.addEventListener('click', () => { el.panel.hidden = false; el.openChat.hidden = true; persist(); });
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('active', x === b));
  document.querySelectorAll('.tab').forEach(t => { t.hidden = t.id !== 'tab-' + b.dataset.tab; });
}));
addEventListener('resize', applyPos);

// ---- settings wiring ----
function applyBg() { document.body.dataset.bg = el.bg.value; }
async function loadModel() {
  $('#loading')?.remove();
  const info = models.find(m => m.id === el.model.value);
  if (!info) return;
  setStatus(t('model.loading'));
  try { await avatar.load(info); setStatus(''); }
  catch (e) { setStatus(t('model.fail') + (e.message || e), true); }
}
el.model.addEventListener('change', () => { persist(); loadModel(); });
for (const k of ['speak', 'lang', 'volume']) el[k].addEventListener('change', persist);
el.follow.addEventListener('change', () => { avatar.setFollow(el.follow.checked); persist(); });
el.volume.addEventListener('input', () => { if (audioEl) audioEl.volume = Number(el.volume.value); });
let lastScene = 0;
el.bg.addEventListener('change', () => {
  applyBg(); persist();
  // She notices the backdrop changing (not more than once a minute, and only if she may speak up on her own).
  if (!el.initiative.checked || busy || !avatar.model || Date.now() - lastScene < 60000) return;
  lastScene = Date.now();
  converse('', 'scene');
});
function showTune() { $('#pitch-val').textContent = el.pitch.value; $('#rate-val').textContent = el.rate.value; }
for (const k of ['pitch', 'rate']) el[k].addEventListener('input', () => { showTune(); persist(); });
$('#voice-test').addEventListener('click', async () => {
  // A scripted sample: also shows the gestures the net can perform.
  const script = t('voice.sample');
  const btn = $('#voice-test');
  btn.disabled = true;
  try { await speak(script.replace(/\[[\w:]+\]\s*/g, ''), parseScript(script)); setStatus(''); }
  catch (e) { setStatus(e.message, true); }
  finally { btn.disabled = false; avatar.setEmotion('neutral'); }
});
el.zoom.addEventListener('input', () => { avatar.setZoom(Number(el.zoom.value)); persist(); });
el.initiative.addEventListener('change', persist);
el.agent.addEventListener('change', persist);
el.work.addEventListener('change', persist);
el.control.addEventListener('change', () => {
  if (el.control.checked && !confirm(t('control.confirm'))) el.control.checked = false;
  persist();
});
el.presence.addEventListener('change', () => { idleLimit = nextIdle(); persist(); });
el.bargein.addEventListener('change', persist);
el.voicenative.addEventListener('change', persist);
el.drag.addEventListener('change', persist);
el.uilang.addEventListener('change', () => {
  setUiLang(el.uilang.value);
  el.lang.value = SPEECH_LANG[uiLang];   // speech recognition follows the app language (it can still be changed below)
  document.title = t('name');
  provRender();
  persist();
});

let models = [];
(async () => {
  const m = await fetch('/api/models').then(r => r.json());
  models = m;
  for (const x of m) el.model.add(new Option(x.name, x.id));
  if (saved.model && m.some(x => x.id === saved.model)) el.model.value = saved.model;
  el.follow.checked = !!saved.follow;
  avatar.follow = el.follow.checked;
  if (saved.volume) el.volume.value = saved.volume;
  if (saved.pitch !== undefined) el.pitch.value = saved.pitch;
  if (saved.rate !== undefined) el.rate.value = saved.rate;
  showTune();
  if (saved.zoom) el.zoom.value = saved.zoom;
  avatar.zoom = Number(el.zoom.value);
  if (saved.initiative === false) el.initiative.checked = false;
  el.presence.checked = !!saved.presence;
  el.bargein.checked = !!saved.bargein;
  if (saved.speak === false) el.speak.checked = false;
  el.lang.value = saved.lang || SPEECH_LANG[uiLang];
  warmRecognizer();
  el.voicenative.checked = !!saved.voicenative;
  el.drag.checked = saved.drag !== false;
  el.agent.checked = saved.agent !== false;
  el.work.checked = saved.work === true;   // off unless she was asked to work
  el.control.checked = DESKTOP && saved.control === true;   // off unless she was given the mouse on purpose
  if (DESKTOP && window.restoreHear) window.restoreHear();   // hearing returns only if "remember my choice" was ticked on purpose
  document.title = t('name');
  if (saved.bg) el.bg.value = saved.bg;
  el.panel.classList.toggle('minimized', !!saved.minimized);
  el.panel.hidden = !!saved.closed;
  el.openChat.hidden = !saved.closed;
  applyBg(); applyPos();
  if (DESKTOP && saved.place) avatar.place = saved.place;
  settingsReady = true;
  await provInit().catch(() => {});   // which network she thinks with: from the server, nothing to type in a console
  if (!m.length) { $('#loading').textContent = t('models.none'); return; }
  await loadModel();
  if (avatar.model && el.initiative.checked && provReady()) setTimeout(() => converse('', 'greet'), 1200);   // greet once per page load
})().catch(() => { settingsReady = true; setStatus(t('models.listfail'), true); });

// ---- desktop mode (Electron): transparent window, click-through, dragging, watching the screen ----
let screenQuietAt = 0;
if (DESKTOP) {
  $('#eye-row').hidden = false;
  $('#media-row').hidden = false;
  $('#hear-row').hidden = false;
  $('#hearkeep-row').hidden = false;
  $('#songid-row').hidden = false;
  $('#control-row').hidden = false;
  $('#drag-row').hidden = false;
  el.mic.title = t('mic.desktop');

  // The window covers the screen; clicks pass through everywhere except Luna's pixels and the interface.
  let interactive = false, dragging = null;
  const setInteractive = on => { if (on !== interactive) { interactive = on; window.desktop.setInteractive(on); } };
  const overUi = t => !!t.closest?.('#panel,#open-chat,#cam,#confirm,#keybox,#diffbox');
  addEventListener('pointermove', e => {
    if (dragging) {
      avatar.setPlace(dragging.px + (e.clientX - dragging.x) / innerWidth, dragging.py + (e.clientY - dragging.y) / innerHeight);
      dragging.moved = dragging.moved || Math.abs(e.clientX - dragging.x) + Math.abs(e.clientY - dragging.y) > 4;
      return;
    }
    const t = document.elementFromPoint(e.clientX, e.clientY);
    // during a task only her stop button takes the mouse: her own clicks must reach the programs underneath
    if (agentRun) { setInteractive(!!t && !!t.closest?.('#hud,#confirm')); return; }
    setInteractive(!!t && (overUi(t) || (t.tagName === 'CANVAS' && avatar.opaqueAt(e.clientX, e.clientY))));
  });
  document.addEventListener('mouseleave', () => { if (!dragging) setInteractive(false); });
  $('#stage').addEventListener('pointerdown', e => {
    if (!el.drag.checked || !avatar.opaqueAt(e.clientX, e.clientY)) return;
    dragging = {x: e.clientX, y: e.clientY, px: avatar.place.x, py: avatar.place.y, moved: false};
    $('#stage').setPointerCapture(e.pointerId);
  });
  const endDrag = () => { if (dragging) { if (dragging.moved) persist(); dragging = null; } };
  $('#stage').addEventListener('pointerup', endDrag);
  $('#stage').addEventListener('pointercancel', endDrag);
  // a drag must not count as the click that interrupts her
  $('#stage').addEventListener('click', e => { if (dragging?.moved) e.stopImmediatePropagation(); }, true);

  // The eye (a setting): while on, and only then, she may look at the screen. Never on at launch; Ctrl+Alt+L is the quick pause.
  let eyeTimer = null;
  el.eye = $('#eye');
  const eye = () => el.eye.checked;
  function setEye(on) {
    el.eye.checked = on;
    if (on) screenTalkUntil = Date.now() + 90000;   // "я включил" is followed by "а сейчас?"
    setStatus(on ? t('eye.on') : t('eye.off'));
    clearTimeout(eyeTimer);
    if (on) scheduleGlance();
  }
  el.eye.addEventListener('change', () => {
    if (el.eye.checked && !confirm(t('eye.confirm'))) { el.eye.checked = false; return; }
    setEye(el.eye.checked);
  });
  window.desktop.onToggleEye(() => { if (eye()) setEye(false); });

  // Media (a setting, off at every launch): every 15 s only the active window's TITLE is read. When it names a film, an anime,
  // a video or a song and stays so for a while, she may comment (the server keeps her from nagging). No picture, no sound.
  el.media = $('#media');
  let mediaTimer = null, mediaSeen = '', mediaSince = 0;
  el.media.addEventListener('change', () => {
    if (el.media.checked && !confirm(t('media.confirm'))) { el.media.checked = false; return; }
    clearInterval(mediaTimer); mediaNow = ''; mediaSeen = '';
    setStatus(el.media.checked ? t('media.on') : t('media.off'));
    if (el.media.checked) mediaTimer = setInterval(pollMedia, 15000);
  });
  async function pollMedia() {
    if (!el.media.checked) return;
    let title = '';
    try { title = await window.desktop.title(); } catch { return; }
    mediaNow = looksMedia(title) ? title : '';   // the server decides what really is media; this only avoids sending other titles
    if (title !== mediaSeen) { mediaSeen = title; mediaSince = Date.now(); return; }
    if (!mediaNow || Date.now() - mediaSince < 40000) return;   // it has to stay on screen for a while
    if (!el.initiative.checked || busy || agentRun || avatar.listening || el.message.value || !avatar.model || !provReady()) return;
    if (Date.now() - lastActivity < 20000 || unanswered >= 1) return;   // you are talking to her, or she waits for an answer
    converse('', 'media', null, mediaNow);
  }

  // Hearing (a setting, off at every launch): every 20 s the server listens to the SPEAKERS (never the microphone) for a few
  // seconds and understands it on this computer; no audio is kept. When music or words keep playing, she may comment.
  el.hear = $('#hear');
  let hearTimer = null, hearKind = '', hearSince = 0, hearBusy = false, lastDance = 0;
  const hearKeep = $('#hearkeep');
  hearKeep.addEventListener('change', persist);
  $('#songid').addEventListener('change', e => {   // off at every launch; switching it on is his own, confirmed choice
    if (e.target.checked && !confirm(t('songid.confirm'))) e.target.checked = false;
  });
  el.hear.addEventListener('change', () => {
    clearInterval(hearTimer); hearKind = '';
    if (el.hear.checked) {
      // a restored choice was confirmed earlier, on purpose, together with "remember my choice"
      if (!hearRestoring && !confirm(t('hear.confirm'))) { el.hear.checked = false; persist(); return; }
      setStatus(t('hear.on'));
      hearTimer = setInterval(pollHear, 20000); pollHear();
    } else { setStatus(t('hear.off')); api('/hear', {on: false}).catch(() => {}); }
    persist();
  });
  window.restoreHear = () => {
    if (!(saved.hearkeep === true && saved.hearon === true)) return;
    hearKeep.checked = true; el.hear.checked = true;
    hearRestoring = true;
    try { el.hear.dispatchEvent(new Event('change')); } finally { hearRestoring = false; }
  };
  async function pollHear() {
    if (!el.hear.checked || hearBusy || busy || agentRun || avatar.speaking || avatar.listening) return;
    hearBusy = true;
    try {
      const title = await window.desktop.title().catch(() => '');
      const r = await (await api('/hear', {on: true, window: title, lang: uiLang})).json();
      if (r.status === 'loading') { setStatus(t('hear.loading')); return; }
      if (r.status === 'error') { setStatus(t('hear.error') + ' ' + (r.error || ''), true); return; }
      const kind = r.kind === 'music' || r.kind === 'voice' ? r.kind : '';
      if (kind !== hearKind) { hearKind = kind; hearSince = Date.now(); return; }
      if (kind === 'music' && !avatar.speaking && !busy && Date.now() - lastDance > 150000 && Math.random() < 0.35) {   // now and then, not all the time
        lastDance = Date.now(); avatar.dance(8 + Math.random() * 6, danceTempo(90 + Math.random() * 40));
      }
      if (!kind || Date.now() - hearSince < 40000) return;   // the same kind of sound for a while
      if (el.media.checked && mediaNow) return;   // the title path already speaks about it
      if (!el.initiative.checked || busy || agentRun || avatar.speaking || avatar.listening || el.message.value || !avatar.model || !provReady()) return;
      if (Date.now() - lastActivity < 20000 || unanswered >= 1) return;
      converse('', 'media', null, '');
    } catch (err) {
      if (err.message === 'missing') { el.hear.checked = false; clearInterval(hearTimer); setStatus(t('hear.missing'), true); }
    } finally { hearBusy = false; }
  }

  // She does not look on a timer: every 10 s a free local check (window title, how much the screen changed) decides.
  // She looks when you switch to another window and things settle, or when the screen has changed a lot over a long time.
  let lastTitle = '';
  const POLL = 10000;
  function scheduleGlance() {
    clearTimeout(eyeTimer);
    lastGlanceAt = Date.now();
    window.desktop.peek().then(s => { lastTitle = s.title; }).catch(() => {});
    eyeTimer = setTimeout(pollScreen, POLL);
  }
  async function pollScreen() {
    if (!eye()) return;
    eyeTimer = setTimeout(pollScreen, POLL);
    if (!el.presence.checked || !el.initiative.checked || busy || avatar.listening || el.message.value || !avatar.model) return;
    if (Date.now() - lastActivity < 20000 || unanswered >= 1) return;   // you are talking to her, or she is waiting for an answer
    const gap = Date.now() - lastGlanceAt;
    if (gap < 45000) return;
    let s;
    try { s = await window.desktop.peek(); } catch { return; }
    const switched = s.title && s.title !== lastTitle, settled = s.change < 0.03;
    if (!((switched && settled) || (gap > 240000 && s.sinceSent > 0.08))) return;
    let shot = null;
    try { shot = await window.desktop.capture(); } catch { return; }
    lastTitle = s.title; lastGlanceAt = Date.now();
    if (shot && eye()) converse('', 'screen', shot.image, shot.title);
  }
}
