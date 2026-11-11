// ---- the journal of her hands: what she really did, and Undo where it can be taken back ----
const journal = {open: false};

async function journalLoad() {
  const box = $('#journal');
  let entries = [];
  try { entries = (await (await api('/journal/list', {})).json()).entries; }
  catch (e) { box.replaceChildren(Object.assign(document.createElement('p'), {className: 'hint error', textContent: e.message})); return; }
  box.replaceChildren();
  if (!entries.length) {
    box.append(Object.assign(document.createElement('p'), {className: 'hint', textContent: t('journal.empty')}));
    return;
  }
  for (const e of entries) {
    const row = document.createElement('div');
    row.className = 'jrow' + (e.ok ? '' : ' failed') + (e.undone ? ' undone' : '');
    const when = document.createElement('small');
    when.textContent = new Date(e.t * 1000).toLocaleString(uiLang, {dateStyle: 'short', timeStyle: 'short'});
    const what = document.createElement('span');
    what.textContent = t('journal.kind.' + e.kind).replace('{x}', e.x) + (e.ok ? '' : ' ' + t('journal.failed')) + (e.undone ? ' ' + t('journal.undone') : '');
    row.append(when, what);
    if (e.canUndo) {
      const b = document.createElement('button');
      b.textContent = t('journal.undo');
      b.onclick = async () => {
        b.disabled = true;
        try { await api('/journal/undo', {id: e.id}); setStatus(t('journal.undid')); }
        catch (er) { setStatus(er.message, true); }
        journalLoad();
      };
      row.append(b);
    }
    box.append(row);
  }
  const clear = document.createElement('button');
  clear.className = 'wide danger';
  clear.textContent = t('journal.clear');
  clear.onclick = async () => {
    if (!confirm(t('journal.clear.confirm'))) return;
    await api('/journal/clear', {}).catch(() => {});
    journalLoad();
  };
  box.append(clear);
}

$('#journal-show').addEventListener('click', () => {
  journal.open = !journal.open;
  $('#journal').hidden = !journal.open;
  $('#journal-show').textContent = t(journal.open ? 'journal.hide' : 'journal.show');
  if (journal.open) journalLoad();
});
// the labels follow the interface language
$('#uilang').addEventListener('change', () => {
  $('#journal-show').textContent = t(journal.open ? 'journal.hide' : 'journal.show');
  if (journal.open) journalLoad();
});
