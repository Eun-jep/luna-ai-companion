// ---- which neural network she thinks with (settings): choose, key dialog, model list, local networks ----
// The server keeps the keys encrypted and never sends one back, only its last four characters.
const prov = {state: null, seq: 0};

/* 'prov:badkey|detail' from the server -> a sentence in the interface language */
/* the server's own Russian messages (the tests and the log know them) -> a sentence in the interface language */
const SERVER_ERR = [
  ['Некорректный запрос озвучки.', 'srv.badvoice'],
  ['Некорректные настройки голоса.', 'srv.badvoice'],
  ['Некорректный запрос.', 'srv.bad'],
  ['Это действие не запрошено или уже устарело.', 'srv.stale'],
  ['Задача не запрошена или устарела.', 'srv.stale'],
  ['Дождись предыдущего ответа.', 'srv.busy'],
  ['API вернул пустой ответ.', 'srv.empty'],
  ['Ошибка приложения.', 'srv.crash'],
  ['Этот файл нельзя прочитать.', 'srv.nofile'],
  ['Эту папку нельзя просмотреть.', 'srv.nodir'],
  ['Не удалось перенести файл.', 'srv.nomove'],
  ['Сервис озвучки вернул пустой звук.', 'srv.novoice'],
  ['Не удалось озвучить', 'srv.novoice'],
  ['Не установлен edge-tts', 'srv.noedge'],
  ['Не удалось открыть: проверь запись в actions.json.', 'srv.noopen'],
  ['Не получилось: проверь название канала', 'srv.channel'],
];

function fixErr(message) {
  const known = SERVER_ERR.find(([ru]) => (message || '').startsWith(ru));
  if (known) return t(known[1]);
  const m = /^(prov|doc|journal|edit|project|update):(\w+)(?:\|(.*))?$/s.exec(message || '');
  if (!m) return message;
  const text = t(m[1] + '.err.' + m[2]);
  return text + (m[3] ? ' (' + m[3] + ')' : '');
}

async function provCall(op, data = {}) {
  const r = await fetch('/provider/' + op, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-App-Token': window.APP_TOKEN}, body: JSON.stringify(data)});
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(fixErr(body.error) || t('err.request'));
  return body;
}

const provItem = id => prov.state && (prov.state.cloud.find(x => x.id === id) || prov.state.local.find(x => x.id === id));
const provReady = () => !!(prov.state && prov.state.ready);

function provRender() {
  const s = prov.state;
  if (!s) return;
  const sel = $('#prov');
  sel.replaceChildren();
  if (!s.active) sel.append(new Option(t('prov.choose'), ''));
  const cloud = document.createElement('optgroup');
  cloud.label = t('prov.cloud');
  for (const c of s.cloud) cloud.append(new Option(c.name + (c.hasKey ? ' ✓' : ''), c.id));
  sel.append(cloud);
  const here = s.local.filter(x => x.running || x.installed || x.id === s.active);
  if (here.length) {
    const local = document.createElement('optgroup');
    local.label = t('prov.local');
    for (const x of here) local.append(new Option(x.name + (x.running ? ' ✓' : ' (' + t('prov.off') + ')'), x.id));
    sel.append(local);
  }
  sel.value = s.active || '';
  const item = provItem(s.active);
  const isCloud = !!s.cloud.find(x => x.id === s.active);
  $('#prov-status').textContent = !s.active ? t('prov.none') : isCloud ? t('prov.keyok').replace('{x}', item.hint) : t('prov.localok');
  $('#prov-keys').hidden = !isCloud;
  // meaning-based memory and tone through this service: only offered where it has an embeddings endpoint, and only on the user's say-so
  const emb = s.embed || {};
  $('#prov-embed-row').hidden = !emb.can;
  $('#prov-embed').checked = !!emb.on;
  $('#prov-embed-d').textContent = t('embed.d').replace('{x}', emb.name || '');
  $('#prov-get').hidden = !isCloud;
  if (isCloud) $('#prov-get').href = item.url;
  // local networks found on this computer that are not connected yet
  const box = $('#prov-local');
  box.replaceChildren();
  for (const x of s.local) {
    if (x.id === s.active || x.dismissed || !x.installed) continue;
    const card = document.createElement('div');
    card.className = 'offer';
    const text = document.createElement('p');
    text.textContent = (x.running && x.models ? t('prov.found').replace('{n}', x.models) : t('prov.installed')).replace('{x}', x.name);
    card.append(text);
    if (x.running && x.models) {
      const row = document.createElement('div');
      row.className = 'row';
      const yes = document.createElement('button');
      yes.className = 'primary';
      yes.textContent = t('prov.connect');
      yes.onclick = () => provConnect(x.id);
      const no = document.createElement('button');
      no.textContent = t('prov.later');
      no.onclick = async () => { prov.state = await provCall('dismiss', {id: x.id}).catch(() => prov.state); provRender(); };
      row.append(yes, no);
      card.append(row);
    }
    box.append(card);
  }
  provModels();
}

// ---- model catalog: short labels from luna/core/catalog.py ----
function catTags(i) {
  if (!i) return [];
  return [i.rec && t('cat.rec'), i.tier && t('cat.' + i.tier), i.free && t('cat.free'), i.vision && t('cat.vision')].filter(Boolean);
}
const catLabel = (m, i) => catTags(i).length ? m + '  —  ' + catTags(i).join(', ') : m;
function catHint() {
  const i = (prov.info || {})[$('#prov-model').value], tags = catTags(i);
  $('#prov-model-hint').textContent = tags.length ? tags.join(' · ') : t('cat.unknown');
}
function catPicks(picks) {
  const box = $('#prov-picks');
  box.hidden = !picks.length;
  $('#prov-picks-list').replaceChildren(...picks.map(p => {
    const row = document.createElement('div'), code = document.createElement('code'), note = document.createElement('span'), copy = document.createElement('button');
    row.className = 'row';
    code.textContent = p.command;
    note.className = 'hint';
    note.textContent = t('cat.size').replace('{gb}', p.gb).replace('{ram}', p.ram) + ' · ' + t('cat.' + p.tier) + (p.vision ? ' · ' + t('cat.vision') : '');
    copy.type = 'button';
    copy.textContent = t('cat.copy');
    copy.addEventListener('click', () => navigator.clipboard.writeText(p.command).then(() => { copy.textContent = t('cat.copied'); }).catch(() => {}));
    row.append(code, copy);
    const wrap = document.createElement('div');
    wrap.append(row, note);
    return wrap;
  }));
}

async function provModels() {
  const s = prov.state, row = $('#prov-model-row'), sel = $('#prov-model'), mine = ++prov.seq;
  if (!s || !s.active) { row.hidden = true; return; }
  row.hidden = false;
  sel.disabled = true;
  sel.replaceChildren(new Option(t('prov.loading'), ''));
  try {
    const {models, info = {}, picks = []} = await provCall('models', {id: s.active});
    if (mine !== prov.seq) return;
    const current = provItem(s.active).model;
    prov.info = info;
    sel.replaceChildren(...models.map(m => new Option(catLabel(m, info[m]), m)));
    catPicks(picks);
    sel.value = models.includes(current) ? current : models[0];
    if (sel.value !== current) await provCall('model', {id: s.active, model: sel.value}).catch(() => {});
    sel.disabled = false;
    catHint();
  } catch (e) {
    if (mine !== prov.seq) return;
    catPicks([]);
    $('#prov-model-hint').textContent = '';
    sel.replaceChildren(new Option(e.message, ''));   // e.g. "the program is not running"
  }
}

async function provConnect(id) {
  try {
    prov.state = await provCall('select', {id});
    setStatus(t('prov.connected').replace('{x}', provItem(id).name));
  } catch (e) { setStatus(e.message, true); }
  provRender();
}

// ---- key dialog ----
let keyResolve = null;
function keyDialog(item, change) {
  const box = $('#keybox'), input = $('#key-input'), err = $('#key-err');
  $('#key-title').textContent = t(change ? 'prov.key.title.change' : 'prov.key.title.new').replace('{x}', item.name);
  const get = $('#key-get');
  get.href = item.url;
  err.textContent = '';
  input.value = '';
  box.dataset.id = item.id;
  box.hidden = false;
  setTimeout(() => input.focus(), 30);
  return new Promise(resolve => { keyResolve = resolve; });
}
function keyClose(ok) {
  $('#keybox').hidden = true;
  $('#key-input').value = '';
  const r = keyResolve;
  keyResolve = null;
  r?.(ok);
}
$('#keyform').addEventListener('submit', async e => {
  e.preventDefault();
  const ok = $('#key-ok'), err = $('#key-err'), id = $('#keybox').dataset.id;
  const key = $('#key-input').value.trim();
  if (!key) { err.textContent = t('prov.err.badkey'); return; }
  ok.disabled = true;
  err.textContent = t('prov.key.checking');
  try {
    const r = await provCall('key', {id, key});
    prov.state = r;
    keyClose(true);
    provRender();
    setStatus(r.warn === 'billing' ? t('prov.warn.billing') : t('prov.connected').replace('{x}', provItem(id).name), r.warn === 'billing');
  } catch (er) { err.textContent = er.message; }
  ok.disabled = false;
});
$('#key-cancel').addEventListener('click', () => keyClose(false));
$('#keybox').addEventListener('keydown', e => { if (e.key === 'Escape') keyClose(false); });

// ---- settings controls ----
$('#prov').addEventListener('change', async () => {
  const sel = $('#prov'), id = sel.value, was = prov.state.active;
  if (!id) return;
  const item = provItem(id);
  if (prov.state.cloud.some(x => x.id === id) && !item.hasKey) {   // no key yet: ask for it; Cancel = nothing changes
    if (!await keyDialog(item, false)) sel.value = was || '';
    return;
  }
  try { prov.state = await provCall('select', {id}); }
  catch (e) { setStatus(e.message, true); sel.value = was || ''; return; }
  provRender();
});
$('#prov-key').addEventListener('click', () => { const item = provItem(prov.state.active); if (item) keyDialog(item, true); });
$('#prov-del').addEventListener('click', async () => {
  const item = provItem(prov.state.active);
  if (!item || !confirm(t('prov.remove.confirm').replace('{x}', item.name))) return;
  try { prov.state = await provCall('clear', {id: item.id}); } catch (e) { setStatus(e.message, true); }
  provRender();
});
$('#prov-model').addEventListener('change', async () => {
  const id = prov.state.active, model = $('#prov-model').value;
  if (!id || !model) return;
  try { prov.state = await provCall('model', {id, model}); catHint(); } catch (e) { setStatus(e.message, true); }
});
$('#prov-embed').addEventListener('change', async () => {
  const box = $('#prov-embed');
  try { prov.state = await provCall('embed', {on: box.checked}); } catch (e) { setStatus(e.message, true); box.checked = !box.checked; }
  provRender();
});
$('#prov-scan').addEventListener('click', async () => {
  const b = $('#prov-scan');
  b.disabled = true;
  try {
    prov.state = await provCall('state');
    for (const x of prov.state.local) x.dismissed = false;   // an explicit search shows everything again
    provRender();
    if (!prov.state.local.some(x => x.installed)) setStatus(t('prov.scan.none'));
  } catch (e) { setStatus(e.message, true); }
  b.disabled = false;
});

/* At launch: read the state; with nothing connected, point at the settings and offer a local network if one is running. */
async function provInit() {
  prov.state = await provCall('state');
  provRender();
  if (provReady()) return;
  if (window.wizardStart && !flags.wizardSeen) { flags.wizardSeen = true; persist(); flushSettings(); wizardStart(); return; }
  document.querySelector('[data-tab="settings"]')?.click();
  setStatus(t('prov.pick'), true);
  const found = prov.state.local.find(x => x.running && x.models && !x.dismissed);
  if (found) askChoice(t('prov.found').replace('{n}', found.models).replace('{x}', found.name),
    [{label: t('prov.connect'), run: () => provConnect(found.id)}],
    () => provCall('dismiss', {id: found.id}).then(s => { prov.state = s; provRender(); }).catch(() => {}));
}
