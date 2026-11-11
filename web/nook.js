// ---- her corner: the notes she keeps for herself, read-only here (the folder is Documents/Luna/Nook) ----
const nookPanel = {open: false};

function nookError(box, message) {
  box.replaceChildren(Object.assign(document.createElement('p'), {className: 'hint error', textContent: message}));
}

async function nookLoad() {
  const box = $('#nook-box');
  let notes = [];
  try { notes = (await (await api('/nook/list', {})).json()).notes; }
  catch (e) { nookError(box, t('nook.err')); return; }
  box.replaceChildren();
  if (!notes.length) {
    box.append(Object.assign(document.createElement('p'), {className: 'hint', textContent: t('nook.empty')}));
    return;
  }
  for (const n of notes) {
    const row = document.createElement('div');
    row.className = 'jrow';
    const when = document.createElement('small');
    when.textContent = new Date(n.t * 1000).toLocaleString(uiLang, {dateStyle: 'short', timeStyle: 'short'});
    const open = document.createElement('button');
    open.textContent = n.title;
    open.onclick = () => nookRead(n);
    row.append(when, open);
    box.append(row);
  }
}

async function nookRead(n) {
  const box = $('#nook-box');
  let text = '';
  try { text = (await (await api('/nook/read', {file: n.file})).json()).text; }
  catch (e) { nookError(box, t('nook.err')); return; }
  const back = document.createElement('button');
  back.textContent = t('nook.back');
  back.onclick = nookLoad;
  const pre = document.createElement('pre');
  pre.textContent = text;
  box.replaceChildren(back, pre);
}

$('#nook-show').addEventListener('click', () => {
  nookPanel.open = !nookPanel.open;
  $('#nook-box').hidden = !nookPanel.open;
  $('#nook-show').textContent = t(nookPanel.open ? 'nook.hide' : 'nook.show');
  if (nookPanel.open) nookLoad();
});
$('#uilang').addEventListener('change', () => {
  $('#nook-show').textContent = t(nookPanel.open ? 'nook.hide' : 'nook.show');
  if (nookPanel.open) nookLoad();
});
