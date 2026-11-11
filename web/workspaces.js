// ---- folders she may add new files to: only the ones you add here (empty by default) ----
async function wsCall(data) {
  return (await (await api('/project/ws', data)).json()).items;
}

function wsRender(items) {
  const box = $('#ws-list');
  box.replaceChildren();
  if (!items.length) {
    box.append(Object.assign(document.createElement('p'), {className: 'hint', textContent: t('ws.empty')}));
    return;
  }
  for (const w of items) {
    const row = document.createElement('div');
    row.className = 'jrow';
    const name = document.createElement('span');
    name.textContent = w.name;
    const where = document.createElement('small');
    where.textContent = w.path;
    const b = document.createElement('button');
    b.textContent = t('ws.remove');
    b.onclick = async () => {
      try { wsRender(await wsCall({op: 'remove', name: w.name})); } catch (e) { setStatus(e.message, true); }
    };
    row.append(name, b, where);
    box.append(row);
  }
}

async function wsLoad() {
  try { wsRender(await wsCall({op: 'list'})); } catch (e) { setStatus(e.message, true); }
}

$('#ws-add').addEventListener('click', async () => {
  const input = $('#ws-path');
  if (!input.value.trim()) return;
  try { wsRender(await wsCall({op: 'add', path: input.value})); input.value = ''; setStatus(t('ws.added')); }
  catch (e) { setStatus(e.message, true); }
});
$('#uilang').addEventListener('change', wsLoad);
wsLoad();
