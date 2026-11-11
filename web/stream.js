// ---- streamer mode (off at every launch): she co-hosts, answers the chat, fills dead air; hands, screen and private memory stay out ----
window.STREAMING = false;
(() => {
  const $s = id => document.getElementById(id);
  const btn = $s('stream-toggle'), chan = $s('stream-channel'), stat = $s('stream-status'), tools = $s('stream-tools');
  const nick = $s('stream-user'), text = $s('stream-text');
  let timer = null, deadGap = 30000, busyStart = false;
  chan.value = saved.streamChannel || '';
  chan.addEventListener('input', () => persist());

  function show(r) {
    btn.textContent = t(window.STREAMING ? 'stream.end' : 'stream.start');
    tools.hidden = !window.STREAMING;
    chan.disabled = window.STREAMING;
    if (!window.STREAMING) { stat.textContent = ''; return; }
    let s = t('stream.live');
    if (r) {
      if (r.channel) s += ' · ' + r.channel + (r.connected ? ' ✓' : ' …');
      s += ' · ' + t('stream.queue').replace('{n}', r.queued || 0);
      if (r.error && !r.connected) s += ' · ' + r.error;
    }
    stat.textContent = s;
  }

  async function tick() {
    if (!window.STREAMING) return;
    let r;
    try { r = await (await api('/stream/status', {})).json(); } catch { return; }
    show(r);
    if (busy || avatar.speaking || avatar.listening || !avatar.model) return;
    if (r.queued > 0) { converse('', 'stream'); return; }
    if (Date.now() - lastActivity > deadGap) {   // dead air: she does not leave the audience in silence
      deadGap = 25000 + Math.random() * 25000;
      converse('', 'idle');
    }
  }

  btn.addEventListener('click', async () => {
    if (busyStart) return;
    busyStart = true;
    try {
      if (!window.STREAMING) {
        if (!confirm(t('stream.confirm'))) return;
        const r = await (await api('/stream/start', {channel: chan.value.trim()})).json();
        window.STREAMING = true;
        persist();
        show(r);
        await whenIdle();
        timer = setInterval(tick, 2500);
        lastActivity = Date.now();
        converse('', 'stream_start');
      } else {
        clearInterval(timer);
        await whenIdle();
        await converse('', 'stream_end');
        await api('/stream/stop', {});
        window.STREAMING = false;
        show();
      }
    } catch (e) { setStatus(e.message, true); }
    finally { busyStart = false; }
  });

  async function say() {
    const v = text.value.trim();
    if (!v) return;
    text.value = '';
    try { await api('/stream/say', {user: nick.value.trim() || t('stream.viewer'), text: v}); } catch (e) { setStatus(e.message, true); }
  }
  $s('stream-say').addEventListener('click', say);
  text.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); say(); } });
  for (const b of document.querySelectorAll('[data-stream-event]')) {
    b.addEventListener('click', async () => {
      const amount = b.dataset.streamEvent === 'donate' || b.dataset.streamEvent === 'raid' ? text.value.trim() : '';
      if (amount) text.value = '';
      try { await api('/stream/event', {kind: b.dataset.streamEvent, name: nick.value.trim() || t('stream.viewer'), amount}); } catch (e) { setStatus(e.message, true); }
    });
  }
  show();
})();
