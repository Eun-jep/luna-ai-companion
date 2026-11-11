const $ = s => document.querySelector(s);
try { setUiLang((window.APP_STATE && window.APP_STATE.ui) || JSON.parse(localStorage.getItem('companion') || '{}').ui || 'en'); } catch { setUiLang('en'); }   // the app's language
document.title = t('name') + ' · ' + t('gr.title');
$('#stats').setAttribute('aria-label', t('gr.stats'));
const fmt = ts => new Date(ts * 1000).toLocaleString(SPEECH_LANG[uiLang], {day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit'});

// the word for a count in the current language: Russian has three forms, English two, Korean and Japanese one
function word(n, key) {
  const forms = t(key), m = n % 100, d = n % 10;
  if (uiLang === 'ru') return m > 10 && m < 20 ? forms[2] : d === 1 ? forms[0] : d > 1 && d < 5 ? forms[1] : forms[2];
  return uiLang === 'en' && n !== 1 ? forms[1] : forms[0];
}
const count = (n, key) => n + (uiLang === 'ko' || uiLang === 'ja' ? '' : ' ') + word(n, key);

function text(tag, content, className) {
  const node = document.createElement(tag);
  node.textContent = content;
  if (className) node.className = className;
  return node;
}

// he can delete one thing she remembers: a fact (kind user / me, key = its text) or a talk (kind episode, key = its start time)
function forgetButton(kind, key) {
  const b = text('button', '×', 'forget');
  b.type = 'button';
  b.title = t('gr.forget');
  b.setAttribute('aria-label', t('gr.forget'));
  b.addEventListener('click', async () => {
    if (!confirm(t('gr.forget.confirm'))) return;
    await fetch('/memory/forget', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-App-Token': window.APP_TOKEN}, body: JSON.stringify({kind, key})}).catch(() => {});
    load();
  });
  return b;
}

function fillFacts(list, items, empty, kind) {
  list.replaceChildren();
  if (!items.length) list.append(text('li', empty, 'empty'));
  for (const s of items) {
    const li = text('li', s);
    li.prepend(forgetButton(kind, s));
    list.append(li);
  }
}

function render(m) {
  $('#name').textContent = t('name');
  const days = Math.max(0, Math.floor((Date.now() / 1000 - m.born) / 86400));
  $('#intro').textContent = days < 1 ? t('gr.under1') : t('gr.age').replace('{n}', count(days, 'gr.days'));
  const stats = [[word(m.sessions, 'gr.meetings'), m.sessions],
    [t('gr.messages'), m.turns], [t('gr.factsyou'), m.user.length], [t('gr.factsself'), m.me.length]];
  $('#stats').replaceChildren(...stats.map(([label, n]) => {
    const box = text('div', '', 'stat');
    box.append(text('b', String(n)), text('span', label));
    return box;
  }));
  $('#user-count').textContent = m.user.length + ' / ' + m.limit;
  $('#me-count').textContent = m.me.length + ' / ' + m.limit;
  fillFacts($('#user'), m.user, t('gr.empty.user'), 'user');
  fillFacts($('#me'), m.me, t('gr.empty.me'), 'me');
  const episodes = $('#episodes');
  episodes.replaceChildren();
  if (!(m.episodes || []).length) episodes.append(text('li', t('gr.empty.episodes'), 'empty'));
  for (const e of [...(m.episodes || [])].reverse()) {
    const li = document.createElement('li');
    li.append(forgetButton('episode', e.t), text('time', fmt(e.end)), text('div', e.text));
    episodes.append(li);
  }

  const v = m.mood.v, e = m.mood.e;   // same thresholds as the server's description
  const feeling = v > 0.5 ? 1 : v >= 0.15 ? 2 : v > -0.1 ? 3 : v > -0.4 ? 4 : 5, energy = e > 0.7 ? 1 : e < 0.3 ? 3 : 2;
  $('#mood-text').textContent = t('gr.f' + feeling) + ' · ' + t('gr.e' + energy);
  $('#mood-v').style.width = Math.round((m.mood.v + 1) / 2 * 100) + '%';
  $('#mood-e').style.width = Math.round(m.mood.e * 100) + '%';
  const wonder = $('#wonder');
  wonder.hidden = !m.wonder;
  wonder.textContent = m.wonder ? t('gr.wants') + m.wonder : '';
  const diary = $('#diary');
  diary.replaceChildren();
  if (!m.diary.length) diary.append(text('li', t('gr.empty.diary'), 'empty'));
  for (const e of [...m.diary].reverse()) {
    const li = document.createElement('li');
    li.append(text('time', fmt(e.t)), text('div', e.text));
    diary.append(li);
  }

  const interests = $('#interests');
  interests.replaceChildren();
  if (!m.interests.length) interests.append(text('li', t('gr.empty.interests'), 'empty'));
  for (const e of [...m.interests].reverse()) {
    const li = document.createElement('li');
    li.append(text('time', fmt(e.t)), text('div', e.title && e.title !== e.topic ? e.topic + ' · ' + e.title : e.topic, 'who'), text('div', e.learned));
    interests.append(li);
  }

  const log = $('#log');
  log.replaceChildren();
  if (!m.log.length) log.append(text('li', t('gr.empty.log'), 'empty'));
  for (const e of [...m.log].reverse()) {
    const li = document.createElement('li');
    li.append(text('time', fmt(e.t)), text('div', e.kind === 'user' ? t('gr.about.you') : t('gr.about.me'), 'who'));
    for (const s of e.add) li.append(text('div', '+ ' + s, 'add'));
    for (const s of e.del) li.append(text('div', '− ' + s, 'del'));
    log.append(li);
  }
}

function load() {
  return fetch('/api/memory', {headers: {'X-App-Token': window.APP_TOKEN}})
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(render)
    .catch(() => { $('#intro').textContent = t('gr.fail'); });
}
load();
