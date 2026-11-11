// ---- first-run wizard: language -> which network she thinks with (+ key) -> how to talk to her ----
// Shown while no network is connected (instead of dropping you into the settings), and from "Setup guide" in the settings.
// It only calls what the settings already use (provCall / setUiLang): no new server route, no new way for a key to travel.
const wizard = {step: 0, pick: null};

function wzEl(tag, props = {}, ...kids) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...kids);
  return node;
}

function wzClose() {
  $('#wizard').hidden = true;
  $('#wizard').replaceChildren();
  if (!provReady()) { document.querySelector('[data-tab="settings"]')?.click(); setStatus(t('prov.pick'), true); }
}

function wzFrame(title, hint, body, actions) {
  const box = $('#wizard');
  box.setAttribute('aria-labelledby', 'wz-title');
  const dots = wzEl('div', {className: 'wz-dots'}, ...[0, 1, 2].map(i => wzEl('i', {className: i === wizard.step ? 'on' : ''})));
  box.replaceChildren(wzEl('div', {id: 'wz-card'}, dots, wzEl('h4', {id: 'wz-title', textContent: title}), wzEl('p', {className: 'hint', textContent: hint}), body, wzEl('div', {className: 'row'}, ...actions)));
  box.hidden = false;
  box.querySelector('button')?.focus();
}

function wzLang() {
  wizard.step = 0;
  const body = wzEl('div', {className: 'wz-grid'});
  for (const [code, name] of [['en', 'English'], ['ru', 'Русский'], ['ko', '한국어'], ['ja', '日本語']]) {
    body.append(wzEl('button', {type: 'button', textContent: name, className: code === uiLang ? 'primary' : '', onclick: () => {
      el.uilang.value = code;
      el.uilang.dispatchEvent(new Event('change'));
      wzLang();
    }}));
  }
  wzFrame(t('wz.lang.title'), t('wz.lang.hint'), body, [wzEl('button', {type: 'button', className: 'primary', textContent: t('wz.next'), onclick: wzBrain})]);
}

function wzBrain() {
  wizard.step = 1;
  const s = prov.state;
  const body = wzEl('div', {className: 'wz-brain'});
  const keyRow = wzEl('form', {className: 'wz-key', hidden: true, autocomplete: 'off'});
  const input = wzEl('input', {type: 'password', autocomplete: 'off', spellcheck: false, placeholder: t('prov.key.ph')});
  const err = wzEl('p', {className: 'hint error', role: 'alert'});
  const link = wzEl('a', {className: 'hint link', target: '_blank', rel: 'noopener', textContent: t('prov.key.get')});
  const save = wzEl('button', {type: 'submit', className: 'primary', textContent: t('prov.key.ok')});
  keyRow.append(input, link, err, save);
  keyRow.addEventListener('submit', async e => {
    e.preventDefault();
    const key = input.value.trim();
    if (!key) { err.textContent = t('prov.err.badkey'); return; }
    save.disabled = true;
    err.textContent = t('prov.key.checking');
    try {
      prov.state = await provCall('key', {id: wizard.pick, key});
      input.value = '';
      provRender();
      wzDone();
    } catch (er) { err.textContent = er.message; }
    save.disabled = false;
  });

  const local = s.local.filter(x => x.running && x.models);
  if (local.length) {
    body.append(wzEl('p', {className: 'wz-label', textContent: t('prov.local')}));
    for (const x of local) {
      body.append(wzEl('button', {type: 'button', textContent: x.name + ' ✓', onclick: async () => {
        try { prov.state = await provCall('select', {id: x.id}); provRender(); wzDone(); } catch (e) { err.textContent = e.message; }
      }}));
    }
  }
  body.append(wzEl('p', {className: 'wz-label', textContent: t('prov.cloud')}));
  const grid = wzEl('div', {className: 'wz-grid'});
  for (const c of s.cloud) {
    grid.append(wzEl('button', {type: 'button', textContent: c.name + (c.hasKey ? ' ✓' : ''), className: wizard.pick === c.id ? 'primary' : '', onclick: async () => {
      wizard.pick = c.id;
      if (c.hasKey) { try { prov.state = await provCall('select', {id: c.id}); provRender(); wzDone(); } catch (e) { err.textContent = e.message; } return; }
      for (const b of grid.children) b.className = b === grid.children[s.cloud.indexOf(c)] ? 'primary' : '';
      link.href = c.url;
      keyRow.hidden = false;
      input.focus();
    }}));
  }
  body.append(grid, keyRow);
  wzFrame(t('wz.brain.title'), t('wz.brain.hint'), body, [wzEl('button', {type: 'button', textContent: t('wz.later'), onclick: wzClose})]);
}

function wzDone() {
  wizard.step = 2;
  const list = wzEl('ul', {className: 'wz-tips'}, ...['wz.tip1', 'wz.tip2', 'wz.tip3'].map(k => wzEl('li', {textContent: t(k)})));
  wzFrame(t('wz.done.title'), t('wz.done.hint'), list, [wzEl('button', {type: 'button', className: 'primary', textContent: t('wz.start'), onclick: () => {
    $('#wizard').hidden = true;
    $('#wizard').replaceChildren();
    document.querySelector('[data-tab="chat"]')?.click();
    if (avatar.model && el.initiative.checked && provReady()) setTimeout(() => converse('', 'greet'), 600);
  }})]);
}

function wizardStart() { wizard.pick = null; wzLang(); }
$('#wizard').addEventListener('keydown', e => { if (e.key === 'Escape') wzClose(); });
$('#wizard-open')?.addEventListener('click', async () => {
  try { prov.state = await provCall('state'); } catch { /* the old state is fine */ }
  wizardStart();
});
