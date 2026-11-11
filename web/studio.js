// ---- the song library: songs the creator added; she performs the recording itself, dancing and moving her mouth to it ----

/* Beats per minute of an audio file (80..160), from where the sound suddenly gets louder; 0 when it cannot be told. */
async function detectTempo(bytes) {
  try {
    const rate = 22050, ctx = new OfflineAudioContext(1, 1, rate);
    const audio = await ctx.decodeAudioData(bytes.slice(0));
    const data = audio.getChannelData(0), hop = 441, frames = Math.min(Math.floor(data.length / hop), 90 * 50);
    if (frames < 200) return {bpm: 0, secs: audio.duration};
    const energy = new Float32Array(frames);
    for (let f = 0; f < frames; f++) { let s = 0; for (let i = f * hop; i < (f + 1) * hop; i++) s += data[i] * data[i]; energy[f] = Math.sqrt(s / hop); }
    const flux = new Float32Array(frames);
    for (let f = 1; f < frames; f++) flux[f] = Math.max(0, energy[f] - energy[f - 1]);
    let best = 0, bestScore = 0;
    for (let lag = 19; lag <= 38; lag++) {   // 50 frames per second: 19..38 frames = 158..79 bpm
      let s = 0;
      for (let f = lag; f < frames; f++) s += flux[f] * flux[f - lag];
      s /= frames - lag;
      if (s > bestScore) { bestScore = s; best = lag; }
    }
    return {bpm: best ? Math.round(3000 / best) : 0, secs: audio.duration};
  } catch { return {bpm: 0, secs: 0}; }
}

const DANCES = ['hop', 'sway', 'hop', 'sway'];
let performing = false;   // a recording is playing: clicking her or Escape stops it (see app.js)
const danceTempo = bpm => Math.max(60, Math.min(80, bpm > 100 ? bpm / 2 : bpm * 0.75));   // half time: a hop on every beat of a real song is too quick

const stopButton = Object.assign(document.createElement('button'), {type: 'button', hidden: true});
stopButton.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:50;padding:8px 18px;border-radius:20px';
stopButton.onclick = () => interrupt();
document.body.append(stopButton);

/* She performs a song from the library: plays the recording, her mouth follows it, she dances on its beat. */
async function performSong(song, mine) {
  if (mine?.cancelled) return;
  setStatus(t('songs.prep').replace('{x}', song.title));
  avatar.thinking = true;
  let url;
  try { url = URL.createObjectURL(await (await api('/studio/file', {id: song.id})).blob()); }
  catch (err) { avatar.thinking = false; setStatus(err.message, true); return; }
  if (mine?.cancelled) { URL.revokeObjectURL(url); avatar.thinking = false; return; }
  addMessage('note', t(song.her ? 'songs.now.her' : 'songs.now').replace('{x}', song.title));
  const bpm = danceTempo(song.bpm || 100);
  let turn = 0;
  const dance = () => avatar.dance(14, bpm, DANCES[turn++ % DANCES.length]);   // a new figure every few seconds
  dance();
  const timer = setInterval(dance, 13500);
  performing = true;
  stopButton.textContent = '■ ' + t('songs.stop');
  stopButton.hidden = false;
  try { await playSpeech(url, '', [{at: 0, tag: 'happy'}]); }
  catch (err) { setStatus(err.message, true); }
  finally { performing = false; stopButton.hidden = true; clearInterval(timer); avatar.dancing = null; }
}

async function songsLoad(songs) {
  const box = $('#songs');
  if (!songs) {
    try { songs = (await (await api('/studio/list', {})).json()).songs; }
    catch (e) { box.replaceChildren(Object.assign(document.createElement('p'), {className: 'hint error', textContent: e.message})); return; }
  }
  box.replaceChildren();
  if (!songs.length) { box.append(Object.assign(document.createElement('p'), {className: 'hint', textContent: t('songs.empty')})); return; }
  for (const s of songs) {
    const row = document.createElement('div');
    row.className = 'jrow';
    row.style.gridTemplateColumns = '1fr auto auto';
    const name = document.createElement('span');
    name.textContent = (s.her ? '♪ ' : '') + s.title + (s.bpm ? ' · ' + s.bpm + ' bpm' : '') + (s.her ? ' · ' + t('songs.her') : '');
    const play = document.createElement('button');
    play.textContent = '▶';
    play.title = t('songs.play');
    play.onclick = () => performSong(s, null);
    const del = document.createElement('button');
    del.textContent = '✕';
    del.title = t('songs.del');
    del.onclick = async () => {
      del.disabled = true;
      try { songsLoad((await (await api('/studio/remove', {id: s.id})).json()).songs); }
      catch (e) { setStatus(e.message, true); del.disabled = false; }
    };
    row.append(name, play, del);
    box.append(row);
  }
}

async function songsAdd(files, her) {
  for (const file of files) {
    setStatus(t('songs.adding').replace('{x}', file.name));
    try {
      const bytes = await file.arrayBuffer();
      const r = await fetch('/studio/add', {method: 'POST', headers: {'X-App-Token': window.APP_TOKEN, 'X-Name': encodeURIComponent(file.name), ...(her ? {'X-Her': '1'} : {}), 'Content-Type': 'application/octet-stream'}, body: bytes});
      if (!r.ok) {
        let code = '';
        try { code = (await r.json()).error; } catch { /* not json */ }
        throw Error(t('songs.bad.' + code) !== 'songs.bad.' + code ? t('songs.bad.' + code) : t('err.request'));
      }
      const added = await r.json();
      const info = await detectTempo(bytes);
      if (info.bpm || info.secs) await api('/studio/info', {id: added.song.id, bpm: info.bpm, secs: info.secs});
      setStatus(t('songs.added').replace('{x}', added.song.title));
    } catch (e) { setStatus(e.message, true); }
  }
  songsLoad();
}

$('#songs-add').addEventListener('click', () => $('#songs-file').click());
$('#songs-file').addEventListener('change', async e => { const files = [...e.target.files]; e.target.value = ''; await songsAdd(files); });
$('#songs-add-her').addEventListener('click', () => $('#songs-file-her').click());
$('#songs-file-her').addEventListener('change', async e => { const files = [...e.target.files]; e.target.value = ''; await songsAdd(files, true); });
songsLoad();
