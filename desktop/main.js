/* Luna on the desktop: a transparent, always-on-top window over the whole screen. The Python server does all the
   thinking; this file only starts it, shows its page, lets clicks pass through empty areas and takes screenshots
   when the page asks for one. */
const {app, BrowserWindow, desktopCapturer, dialog, globalShortcut, ipcMain, Menu, screen, session, Tray} = require('electron');
const {spawn} = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');

// Everything the shell and the server print goes to shell.log next to her data, so "it does not start" always has an answer.
const LOG = path.join(process.env.APPDATA || require('os').homedir(), 'Luna', 'shell.log');
function note(text) {
  try {
    fs.mkdirSync(path.dirname(LOG), {recursive: true});
    if (fs.existsSync(LOG) && fs.statSync(LOG).size > 512 * 1024) fs.renameSync(LOG, LOG + '.old');   // never grows without bound
    fs.appendFileSync(LOG, new Date().toISOString() + ' ' + text.trimEnd() + '\n');
  } catch { /* a log that cannot be written must not stop her */ }
}
process.on('uncaughtException', e => { note('uncaught: ' + (e.stack || e)); });
let server = null;
let win = null;
let tray = null;

function startServer() {
  return new Promise((resolve, reject) => {
    // the project's own virtual environment has the libraries (numpy, ...); the system Python usually does not
    const venvPy = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
    server = spawn(require('fs').existsSync(venvPy) ? venvPy : 'py', ['-u', 'app.py'], {cwd: ROOT, env: {...process.env, COMPANION_NO_BROWSER: '1', PYTHONIOENCODING: 'utf-8'}});
    let log = '';
    const onData = chunk => {
      note('server: ' + chunk.toString('utf8'));
      log += chunk.toString('utf8');
      const m = log.match(/Open:\s*(http:\/\/127\.0\.0\.1:\d+)/);
      if (m) resolve(m[1]);
    };
    server.stdout.on('data', onData);
    server.stderr.on('data', onData);
    server.on('exit', code => reject(Error('Сервер остановился (код ' + code + ').\n' + log.slice(-800))));
    server.on('error', reject);
    setTimeout(() => reject(Error('Сервер не ответил за 30 секунд.\n' + log.slice(-800))), 30000);
  });
}

async function createWindow(url) {
  const area = screen.getPrimaryDisplay().workArea;
  win = new BrowserWindow({
    x: area.x, y: area.y, width: area.width, height: area.height,
    transparent: true, frame: false, hasShadow: false, resizable: false, movable: false, focusable: true,
    alwaysOnTop: true, skipTaskbar: false, backgroundColor: '#00000000', title: 'Луна',
    webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false,
                     autoplayPolicy: 'no-user-gesture-required', backgroundThrottling: false}});   // timers keep running while she sleeps in the tray
  win.setAlwaysOnTop(true, 'screen-saver');
  win.setIgnoreMouseEvents(true, {forward: true});   // empty areas let clicks through; the page switches this on over Luna and the panel
  win.setMenuBarVisibility(false);
  await win.loadURL(url);
}

// The page needs to know where the mouse is even while the window ignores it. Windows forwards those moves unreliably, so the
// cursor is read here and handed to the page, which decides (as before) whether the point is Luna or her interface.
setInterval(() => {
  if (!win || win.isDestroyed() || !win.isVisible()) return;
  const p = screen.getCursorScreenPoint(), b = win.getContentBounds();
  win.webContents.send('cursor', {x: p.x - b.x, y: p.y - b.y});
}, 50);

ipcMain.on('interactive', (_event, on) => { win?.setIgnoreMouseEvents(!on, {forward: true}); });
ipcMain.on('quit', () => app.quit());

// ---- living in the tray: hidden she keeps running and can wake up for a date she remembers ----
function showLuna() { if (win) { win.show(); win.setAlwaysOnTop(true, 'screen-saver'); } }
function toggleLuna() { if (win?.isVisible()) win.hide(); else showLuna(); updateTray(); }
function updateTray() {
  tray?.setContextMenu(Menu.buildFromTemplate([
    {label: win?.isVisible() ? 'Спрятать Луну' : 'Показать Луну', click: toggleLuna},
    {type: 'separator'},
    {label: 'Выйти', click: () => app.quit()}]));
}
function makeTray() {
  tray = new Tray(path.join(__dirname, 'tray.png'));
  tray.setToolTip('Луна');
  tray.on('click', toggleLuna);
  updateTray();
}
ipcMain.on('wake', () => { if (!win?.isVisible()) { showLuna(); updateTray(); } });   // the page wants to speak: bring her back

// ---- looking at the screen ----
const OWN_TITLES = new Set(['', 'Компаньон', 'Луна', 'Program Manager']);
let prevFrame = null, sentFrame = null;

// Title of the topmost ordinary window (the window list comes in z-order, top first): a free hint of what she is doing.
async function topTitle() {
  const windows = await desktopCapturer.getSources({types: ['window'], thumbnailSize: {width: 0, height: 0}});
  return (windows.find(w => !OWN_TITLES.has(w.name.trim())) || {name: ''}).name.trim();
}

// A tiny copy of the screen to tell how much it changed (0 = same, 1 = completely different).
async function smallFrame() {
  const [source] = await desktopCapturer.getSources({types: ['screen'], thumbnailSize: {width: 64, height: 36}});
  return source ? source.thumbnail.toBitmap() : null;
}
function difference(a, b) {
  if (!a || !b || a.length !== b.length) return 1;
  let sum = 0;
  for (let i = 0; i < a.length; i += 4) sum += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]);
  return sum / (a.length / 4 * 3 * 255);
}

// Only the title of the active window (for noticing a film, an anime or a song). No picture, no sound.
ipcMain.handle('title', () => topTitle().catch(() => ''));

// Cheap local check, no picture leaves the computer: window title, change since the last check and since the last sent picture.
ipcMain.handle('peek', async () => {
  const [title, frame] = await Promise.all([topTitle(), smallFrame()]);
  const result = {title, change: difference(prevFrame, frame), sinceSent: difference(sentFrame, frame)};
  prevFrame = frame;
  return result;
});

// One screenshot of the primary display, scaled down, as a JPEG data URL. Only called while "look at the screen" is on.
ipcMain.handle('capture', async (_event, big) => {   // big: a sharper picture for a mouse-and-keyboard task
  const display = screen.getPrimaryDisplay();
  const sources = await desktopCapturer.getSources({types: ['screen'], thumbnailSize: big ? {width: 1600, height: 1000} : {width: 1280, height: 800}});
  const source = sources.find(s => String(s.display_id) === String(display.id)) || sources[0];
  if (!source) return null;
  if (!big) sentFrame = await smallFrame();
  return {image: 'data:image/jpeg;base64,' + source.thumbnail.toJPEG(big ? 72 : 65).toString('base64'), title: await topTitle()};
});

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => callback(permission === 'media'));   // camera for face tracking
  try {
    await createWindow(await startServer());
  } catch (e) {
    console.error(e.message);
    note('start failed: ' + e.message);
    // a window with the reason instead of a console that closes: the missing library, the busy port, whatever the server printed
    dialog.showErrorBox('Луна не запустилась', e.message + '\n\nПодробности: ' + LOG +
      (/No module named/.test(e.message) ? '\n\nНе хватает библиотеки. Выполните:  py -m pip install -r requirements.txt' : ''));
    app.quit();
    return;
  }
  globalShortcut.register('Control+Alt+L', () => win?.webContents.send('toggle-eye'));   // quick pause of screen watching
  globalShortcut.register('Control+Alt+K', () => win?.webContents.send('stop-agent'));   // emergency stop of a mouse-and-keyboard task
  globalShortcut.register('Control+Alt+Q', () => app.quit());
  globalShortcut.register('Control+Alt+H', toggleLuna);   // hide to the tray / bring back
  try { makeTray(); } catch (e) { console.error('Нет значка в трее: ' + e.message); }   // she works without it
});

app.on('will-quit', () => { globalShortcut.unregisterAll(); server?.kill(); });
app.on('window-all-closed', () => app.quit());
