// ---- settings -> Updates: ask the feed, install on a press, roll back. Nothing is installed without a press. ----
const upd = {state: null, offer: null};

function updRender(text, isError = false) {
  $('#upd-status').textContent = text;
  $('#upd-status').classList.toggle('error', isError);
  $('#upd-install').hidden = !upd.offer;
  $('#upd-rollback').hidden = !(upd.state && upd.state.backup);
  $('#upd-check').disabled = !(upd.state && upd.state.feed);
}

async function updCall(op) {
  const r = await fetch('/update/' + op, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-App-Token': window.APP_TOKEN}, body: '{}'});
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(fixErr(body.error) || t('err.request'));
  return body;
}

async function updCheck(quiet) {
  if (!upd.state || !upd.state.feed) return;
  $('#upd-check').disabled = true;
  updRender(t('upd.checking'));
  try {
    const r = await updCall('check');
    upd.offer = r.available ? r : null;
    updRender(r.available ? t('upd.available').replace('{x}', r.version) + (r.notes ? ' — ' + r.notes : '') : t('upd.uptodate').replace('{x}', r.current));
  } catch (e) { updRender(quiet ? t('upd.uptodate').replace('{x}', upd.state.current) : e.message, !quiet); }
  $('#upd-check').disabled = false;
}

function updIdle() {
  updRender(upd.state.feed ? t('upd.current').replace('{x}', upd.state.current) : t('upd.nofeed').replace('{x}', upd.state.current));
}
// the line was composed in the language of that moment: switching language (the wizard does) must redo it
addEventListener('uilang', () => { if (upd.state && !upd.offer) updIdle(); });

async function updInit() {
  try { upd.state = await updCall('state'); } catch { return; }
  updIdle();
  if (upd.state.feed) updCheck(true);   // one quiet look at the feed per page load; it only reports
}

$('#upd-check').addEventListener('click', () => updCheck(false));
$('#upd-install').addEventListener('click', async () => {
  if (!upd.offer || !confirm(t('upd.confirm').replace('{x}', upd.offer.version))) return;
  $('#upd-install').disabled = true;
  updRender(t('upd.installing'));
  try {
    const r = await updCall('install');
    upd.offer = null;
    upd.state = await updCall('state');
    updRender(t('upd.installed').replace('{x}', r.version));
  } catch (e) { updRender(e.message, true); }
  $('#upd-install').disabled = false;
});
$('#upd-rollback').addEventListener('click', async () => {
  if (!confirm(t('upd.rollback.confirm'))) return;
  try {
    const r = await updCall('rollback');
    upd.state = await updCall('state');
    updRender(t('upd.rolled').replace('{x}', r.version));
  } catch (e) { updRender(e.message, true); }
});
updInit();
