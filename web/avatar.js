/* Live2D avatar. The neural net writes a "script" (speech + inline directions such as
   [happy] [nod] [look:up]); this file plays it on the model in time with the voice, and adds
   autonomous life (breathing, blinking, eye saccades, glances, listening reactions).
   The models are VTube Studio rigs without motions, so everything is driven through standard
   Cubism parameters, written every frame. */
window.PIXI = PIXI;

// Generic emotion = offsets added to a parameter's default value. Works on any standard rig.
const EMOTION_PARAMS = {
  neutral:   {},
  happy:     {ParamMouthForm: .8, ParamEyeLSmile: .8, ParamEyeRSmile: .8, ParamBrowLY: .3, ParamBrowRY: .3},
  sad:       {ParamMouthForm: -.8, ParamBrowLY: -.4, ParamBrowRY: -.4, ParamBrowLAngle: .6, ParamBrowRAngle: .6, ParamEyeLOpen: -.2, ParamEyeROpen: -.2},
  angry:     {ParamMouthForm: -.5, ParamBrowLForm: -.8, ParamBrowRForm: -.8, ParamBrowLY: -.5, ParamBrowRY: -.5},
  surprised: {ParamBrowLY: .9, ParamBrowRY: .9, ParamEyeLOpen: .3, ParamEyeROpen: .3, ParamMouthForm: .1},
  shy:       {ParamMouthForm: .3, ParamEyeLSmile: .4, ParamEyeRSmile: .4, ParamBrowLY: .1, ParamBrowRY: .1},
  love:      {ParamMouthForm: .9, ParamEyeLSmile: .9, ParamEyeRSmile: .9, ParamBrowLY: .3, ParamBrowRY: .3},
  confused:  {ParamBrowRY: .6, ParamBrowLY: -.2, ParamMouthForm: -.3, ParamBrowLAngle: .3},
  excited:   {ParamMouthForm: 1, ParamEyeLSmile: .6, ParamEyeRSmile: .6, ParamBrowLY: .5, ParamBrowRY: .5},
  disgusted: {ParamMouthForm: -.7, ParamBrowLY: -.3, ParamBrowRY: -.3, ParamBrowLAngle: .5, ParamBrowRAngle: .5, ParamEyeLOpen: -.35, ParamEyeROpen: -.35},
  scared:    {ParamMouthForm: -.4, ParamBrowLY: .7, ParamBrowRY: .7, ParamBrowLAngle: .6, ParamBrowRAngle: .6, ParamEyeLOpen: .3, ParamEyeROpen: .3},
};
// How lively the idle sway is for each mood.
const ENERGY = {neutral: 1, happy: 1.3, sad: 0.55, angry: 1.15, surprised: 1.2, shy: 0.8, love: 1.1, confused: 0.9, excited: 1.7, disgusted: 0.8, scared: 1.4};

// Model-specific .exp3.json files (blush, tears, heart eyes…) are matched by file name.
// Gag toggles like "black face" are deliberately not mapped.
const EXPRESSION_KEYWORDS = {
  shy: /脸红|害羞|羞|blush/i,
  sad: /哭|泪|眼泪|cry|tear/i,
  angry: /生气|怒|angry/i,
  surprised: /惊讶|surpris/i,
  love: /爱心|心心|heart|love/i,
  confused: /疑惑|question/i,
  excited: /星星|star/i,
  disgusted: /白眼|white ?eyes/i,
  scared: /慌张|惊恐|panic/i,
};
// The model's own faces she can show on purpose, [fx:name] (server: faces.py says what each means and keeps them rare).
const FX_KEYWORDS = {
  tears: /哭|泪|眼泪|流泪|cry|tear/i, blush: /脸红|害羞|羞|blush/i, hearts: /爱心|心心|heart|love/i, stars: /星星|star/i,
  anger: /生气|怒|angry/i, shock: /惊讶|surpris/i, confused: /疑惑|question/i, gloom: /黑脸|脸黑|dark ?face/i,
  eyeroll: /白眼|white ?eyes/i, panic: /慌张|惊恐|panic/i, tongue: /舌头|tongue/i, smirk: /歪嘴/i,
  money: /金钱眼|money/i, squint: /眯眯眼|笑咪咪|笑眯眯/i, sweat: /黑线/i,
};
const FX_SECONDS = 3;
// The model's own movement files (VTube rigs often carry a few loose .motion3.json): matched by file name to a meaning the server knows (faces.py MOTIONS).
const MOTION_KEYWORDS = {
  wave: /huishou|挥手|wave/i, wink: /meiyan|媚眼|wink/i, curious: /haoqi|好奇|curio/i, headshake: /yaotou|摇头/i,
  sleepy: /keshui|瞌睡|sleep|doze/i, photo: /zhaoxiang|照相|photo|selfie/i, wings: /chibang|翅膀|wing/i, glasses: /zhaiyan|摘眼镜|glasses/i,
};
const MOTION_MAX = 6;   // seconds: a longer file is cut

/* One value of a Live2D motion curve at time t. Segments: [t0, v0, type, points..., type, points...]; 0 linear, 1 bezier (3 points), 2 stepped, 3 inverse stepped. */
function curveValue(seg, t) {
  let px = seg[0], py = seg[1], i = 2;
  if (t <= px) return py;
  while (i + 2 < seg.length) {
    if (seg[i] === 1) {
      const [x1, y1, x2, y2, x3, y3] = seg.slice(i + 1, i + 7);
      if (t <= x3) {
        const at = (a, b, c, d, u) => (1 - u) ** 3 * a + 3 * (1 - u) ** 2 * u * b + 3 * (1 - u) * u * u * c + u ** 3 * d;
        let lo = 0, hi = 1;
        for (let k = 0; k < 18; k++) { const u = (lo + hi) / 2; if (at(px, x1, x2, x3, u) < t) lo = u; else hi = u; }
        return at(py, y1, y2, y3, (lo + hi) / 2);
      }
      px = x3; py = y3; i += 7;
    } else {
      const x = seg[i + 1], y = seg[i + 2];
      if (t <= x) return seg[i] === 0 ? py + (y - py) * (t - px) / Math.max(1e-6, x - px) : seg[i] === 2 ? py : y;
      px = x; py = y; i += 3;
    }
  }
  return py;
}
const exText = ex => ex.name + ' ' + (ex.label || '');   // what an expression file is about: its file name and its parameter's display name

// Where the eyes go for [look:X]; x>0 = viewer's right, y>0 = up.
const LOOK = {user: [0, 0], left: [-0.9, 0.05], right: [0.9, 0.05], up: [-0.35, 0.85], down: [0, -0.8], away: [0.75, -0.45]};
const GESTURE_LENGTH = {nod: 0.9, shake: 1.0, tilt: 1.9, wink: 0.5, lean: 1.8,
  shrug: 1.5, bow: 1.9, giggle: 1.4, puff: 1.7, blush: 3.2, sigh: 2.3, bounce: 1.3};

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const DESKTOP = !!window.desktop;   // running inside the Electron shell (start-desktop.bat)
if (DESKTOP) document.body.classList.add('desktop');
const approach = (cur, target, rate, dt) => cur + (target - cur) * (1 - Math.exp(-rate * dt));
const rand = (a, b) => a + Math.random() * (b - a);

/* "[happy] Hi! [nod] Nice to hear you." -> cues at relative positions 0..1 of the spoken text. */
function parseScript(script) {
  const re = /\[(\w+)(?::(\w+))?\]/g;
  let text = '', last = 0, m;
  const cues = [];
  while ((m = re.exec(script))) {
    text += script.slice(last, m.index);
    last = re.lastIndex;
    cues.push({pos: text.length, tag: m[1].toLowerCase() + (m[2] ? ':' + m[2].toLowerCase() : '')});
  }
  text += script.slice(last);
  const len = Math.max(1, text.length);
  return cues.map(c => ({at: c.pos / len, tag: c.tag}));
}

class Avatar {
  constructor(host) {
    this.app = new PIXI.Application({resizeTo: host, backgroundAlpha: 0, antialias: true, autoDensity: true,
                                     preserveDrawingBuffer: DESKTOP, resolution: window.devicePixelRatio || 1});
    this.place = {x: 0.82, y: 0.28};   // desktop mode: where her head top sits, as fractions of the screen (she can be dragged)
    host.appendChild(this.app.view);
    this.model = null;
    this.zoom = 1.8;
    this.baseScale = 1;
    this.expressions = [];   // [{name, params:[{Id,Value,Blend}], weight}]
    this.emotion = 'neutral';
    this.emotionMix = {};    // smoothed weight per emotion
    this.fx = {};            // special faces being shown: name -> until (model time)
    this.motionDefs = [];    // the model's own movement files: [{name, url}]
    this.motionCache = {};   // url -> parsed file
    this.motion = null;      // the one playing: {curves, t0, dur}
    this.energy = 1;
    this.mouth = 0;
    this.level = 0;          // live audio level, 0..1 (set by the audio pipeline)
    this.speaking = false;
    this.thinking = false;   // waiting for the model's reply
    this.listening = false;  // microphone is open
    this.follow = false;     // eyes follow the mouse instead of the net's directions
    this.blink = {next: 2, t: -1};
    this.gaze = {x: 0, y: 0};
    this.gazeTarget = LOOK.user;
    this.gazeUntil = 0;
    this.saccade = {x: 0, y: 0, next: 1};
    this.glanceNext = 5;
    this.browFlick = {next: 7, t: -1};
    this.nodNext = 3;
    this.userPos = null;     // where the camera sees the user's face, in gaze units (set by Vision)
    this.absent = false;     // the camera sees nobody
    this.mood = {v: 0.2, e: 0.5};   // long-term mood set by app.js from the server
    this.neutralW = 1;
    this.liveliness = 2;    // multiplier for idle motion and gestures: always the maximum (clamped below)
    this.pose = {x: 0, y: 0, z: 0, bx: 0, bz: 0};   // wandering head/body pose, smoothed toward a target
    this.poseTarget = {...this.pose};
    this.poseNext = 0;
    this.levelSlow = 0;      // slow average of the audio level, to detect speech beats
    this.beatNext = 0;
    this.vowel = 0;          // -1 round (o/u) .. +1 wide (i/e), from the audio spectrum
    this.vowelSmooth = 0;
    this.idleNext = 12;
    this.smileUntil = 0;
    this.gestures = [];      // [{type, t0, dur, dir, amp}]
    this.script = null;      // {cues:[{t, tag}], i, clock}
    this.time = 0;
    // PIXI resizes its canvas asynchronously, so refit on its own event, not window 'resize'.
    this.app.renderer.on('resize', () => this.fit());
  }

  async load(info) {
    if (this.model) {
      this.app.stage.removeChild(this.model);
      this.model.destroy();
      this.model = null;
    }
    const model = await PIXI.live2d.Live2DModel.from(info.url, {autoInteract: false});
    this.model = model;
    this.app.stage.addChild(model);
    this.motionDefs = info.motions || [];
    this.motionCache = {};
    this.motion = null;
    this.expressions = [];
    await Promise.all(info.expressions.map(async e => {
      try {
        const data = await (await fetch(e.url)).json();
        const params = data.Parameters || [];
        // a file named 1 or Button7 says nothing: the display name of its parameter does (blush, tears, ...)
        this.expressions.push({name: e.name, label: ((info.labels || {})[(params[0] || {}).Id]) || '', params, weight: 0});
      } catch { /* a broken optional expression file must not block the model */ }
    }));
    this.core = model.internalModel.coreModel;
    this.defaults = new Map();
    this.touched = new Set();
    model.internalModel.on('afterMotionUpdate', () => this.drive());
    this.fit();
    this.setFollow(this.follow);
  }

  fit() {
    const m = this.model;
    if (!m) return;
    const {width: W, height: H} = this.app.screen;
    // Container bounds are 0 until the first render, so size from the model's own canvas.
    const {originalWidth: mw, originalHeight: mh} = m.internalModel;
    // zoom 1 = full body fits the window; larger values crop towards the head (top-anchored).
    // On the desktop she is a figure about 70 % of the screen high (at the default zoom) that can be moved around.
    this.baseScale = DESKTOP ? H * 0.7 / mh * (this.zoom / 1.8) : Math.min(H * 0.96 / mh, W * 0.9 / mw) * this.zoom;
    m.scale.set(this.baseScale);
    m.anchor.set(0.5, 0);
    this.basePos = DESKTOP ? {x: W * this.place.x, y: H * this.place.y} : {x: W / 2, y: H * 0.02};
    m.position.set(this.basePos.x, this.basePos.y);
  }

  /* Desktop click-through: is there a visible pixel of her under this point? */
  opaqueAt(x, y) {
    const gl = this.app.renderer.gl, view = this.app.renderer.view;
    if (!gl || !this.model) return false;
    const px = new Uint8Array(4), k = view.width / innerWidth;
    gl.readPixels(Math.round(x * k), Math.round(view.height - y * k), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return px[3] > 24;
  }

  setPlace(x, y) {
    this.place = {x: clamp(x, -0.3, 1.3), y: clamp(y, -3, 0.95)};
    this.fit();
  }

  setZoom(z) { this.zoom = z; this.fit(); }

  setFollow(on) {
    this.follow = on;
    window.onpointermove = on ? e => this.model && this.model.focus(e.clientX, e.clientY) : null;
    if (!on && this.model) this.model.internalModel.focusController.focus(0, 0);
  }

  /* A little dance for a few seconds: hops up and down on the beat and a gentle sway from side to side (or only the sway).
     Eases in and out; called now and then, never all the time. */
  dance(seconds = 8, bpm = 100, style = null) {
    this.dancing = {t0: this.time, dur: clamp(seconds, 2, 60), period: 60 / clamp(bpm, 60, 140), style: style || (Math.random() < 0.55 ? 'hop' : 'sway')};
  }

  /* Which movements of its own this model has (names the server knows: see MOTION_KEYWORDS). */
  availableMotions() {
    return Object.keys(MOTION_KEYWORDS).filter(n => this.motionDefs.some(d => MOTION_KEYWORDS[n].test(d.name)));
  }

  /* Play one of the model's own movements once, blended in and out over what the avatar is doing. */
  async playMotion(name) {
    const def = MOTION_KEYWORDS[name] && this.motionDefs.find(d => MOTION_KEYWORDS[name].test(d.name));
    if (!def || this.motion) return;
    try {
      if (!this.motionCache[def.url]) this.motionCache[def.url] = await (await fetch(def.url)).json();
      const data = this.motionCache[def.url];
      const curves = (data.Curves || []).filter(c => c.Target === 'Parameter' && Array.isArray(c.Segments) && c.Segments.length >= 3);
      const dur = Math.min(MOTION_MAX, Math.max(0.5, (data.Meta || {}).Duration || 2));
      this.motion = {curves, t0: this.time, dur};
    } catch { /* a broken optional movement file must not stop her */ }
  }

  /* Which special faces this model has (names the server knows: see FX_KEYWORDS). */
  availableFx() {
    return Object.keys(FX_KEYWORDS).filter(n => this.expressions.some(ex => FX_KEYWORDS[n].test(exText(ex))));
  }

  setEmotion(name) { this.emotion = EMOTION_PARAMS[name] ? name : 'neutral'; }

  /* Execute one direction from the script: [happy], [nod], [look:left]. */
  perform(tag) {
    if (EMOTION_PARAMS[tag]) return this.setEmotion(tag);
    if (tag.startsWith('mo:')) return void this.playMotion(tag.slice(3));
    if (tag.startsWith('fx:')) {
      if (FX_KEYWORDS[tag.slice(3)]) this.fx[tag.slice(3)] = this.time + FX_SECONDS;
      return;
    }
    if (tag.startsWith('look:')) {
      const dir = LOOK[tag.slice(5)];
      if (!dir) return;
      // People blink when their eyes jump somewhere new.
      if (Math.hypot(dir[0] - this.gazeTarget[0], dir[1] - this.gazeTarget[1]) > 0.5 && Math.random() < 0.8) this.triggerBlink();
      this.gazeTarget = dir;
      this.gazeUntil = tag === 'look:user' ? 0 : this.time + 2.4;   // glances return to the viewer
      this.glanceNext = this.time + rand(5, 9);
      return;
    }
    if (GESTURE_LENGTH[tag]) {
      this.gestures.push({type: tag, t0: this.time, dur: GESTURE_LENGTH[tag], dir: Math.random() < 0.5 ? -1 : 1});
    }
  }

  triggerBlink() {
    if (this.blink.t < 0) { this.blink.t = 0; this.blink.double = Math.random() < 0.15; }
  }

  /* Play script cues; `clock` returns seconds since speech began, `duration` is its length. */
  playScript(cues, duration, clock) {
    this.script = {cues: cues.map(c => ({t: c.at * duration, tag: c.tag})), i: 0, clock};
  }

  stopScript() {
    if (!this.script) return;
    // Fire what is left so the final mood and gaze are not lost if audio ended slightly early.
    for (const c of this.script.cues.slice(this.script.i)) this.perform(c.tag);
    this.script = null;
  }

  def(id) {
    if (!this.defaults.has(id)) {
      const i = this.core.getParameterIndex(id);
      this.defaults.set(id, i < 0 ? null : this.core.getParameterDefaultValue(i));
    }
    return this.defaults.get(id);
  }

  drive() {
    const now = performance.now() / 1000;
    const dt = Math.min(now - (this.last || now), 0.1);
    this.last = now;
    this.time += dt;
    const t = this.time, offs = {}, add = (id, v) => { offs[id] = (offs[id] || 0) + v; };

    // --- cues from the script ---
    if (this.script) {
      const s = this.script, clock = s.clock();
      while (s.i < s.cues.length && s.cues[s.i].t <= clock) this.perform(s.cues[s.i++].tag);
    }

    // --- mood energy scales the idle sway ---
    // Her long-term mood (from the server) shifts the baseline: a livelier day moves more, a sad one droops.
    const mood = this.mood;
    this.energy = approach(this.energy, (ENERGY[this.emotion] || 1) * (0.7 + 0.6 * mood.e), 3, dt);
    const e = this.energy;
    this.neutralW = approach(this.neutralW, this.emotion === 'neutral' ? 1 : 0, 4, dt);
    add('ParamMouthForm', mood.v * 0.3 * this.neutralW);                          // faint smile or frown at rest
    add('ParamBrowLY', Math.min(0, mood.v) * 0.3 * this.neutralW);
    add('ParamBrowRY', Math.min(0, mood.v) * 0.3 * this.neutralW);
    add('ParamAngleY', -clamp(0.4 - mood.e, 0, 0.4) * 10);                        // sleepy head

    // --- idle: breathing and an organic head/body wander ---
    // Every few seconds the head picks a new resting pose and eases into it, which reads far more
    // natural than a fixed sine sway. Mood (energy) and the Liveliness setting scale the range.
    const L = this.liveliness, gl = clamp(L, 0.4, 1.6);
    add('ParamBreath', (Math.sin(t * 1.9 * (0.8 + e * 0.2)) + 1) / 2);
    if (t > this.poseNext) {
      const a = e * L;
      this.poseTarget = {x: rand(-6, 6) * a, y: rand(-3.5, 3.5) * a, z: rand(-4, 4) * a, bx: rand(-3, 3) * a, bz: rand(-2, 2) * a};
      this.poseNext = t + rand(1.8, 4.5);
    }
    for (const k in this.pose) this.pose[k] = approach(this.pose[k], this.poseTarget[k], 1.4, dt);
    add('ParamAngleX', this.pose.x + Math.sin(t * 0.9) * 0.8 * L);
    add('ParamAngleY', this.pose.y + Math.sin(t * 0.6 + 1) * 0.6 * L);
    add('ParamAngleZ', this.pose.z);
    add('ParamBodyAngleX', this.pose.bx + Math.sin(t * 0.55) * 0.8 * L);
    add('ParamBodyAngleZ', this.pose.bz);

    // --- idle acts: when nobody is talking, glance around, tilt, or smile to herself ---
    if (!this.speaking && !this.thinking && !this.listening && t > this.idleNext) {
      this.idleNext = t + rand(10, 22) / Math.max(0.4, L);
      const r = Math.random();
      if (r < 0.45) this.perform('look:' + ['left', 'right', 'up', 'down', 'away'][Math.floor(Math.random() * 5)]);
      else if (r < 0.7) this.perform('tilt');
      else if (r < 0.88 && this.emotion === 'neutral') { this.setEmotion('happy'); this.smileUntil = t + 2.2; }
      else this.browFlick.next = 0;
    }
    if (this.smileUntil && t > this.smileUntil) { this.smileUntil = 0; if (this.emotion === 'happy') this.setEmotion('neutral'); }

    // --- gaze: the net's [look:X] target, eye saccades, thinking/listening, glances while talking ---
    if (this.gazeUntil && t > this.gazeUntil) { this.gazeTarget = LOOK.user; this.gazeUntil = 0; }
    if (this.speaking && !this.gazeUntil && t > this.glanceNext) {
      // People glance away while forming a thought; nobody stares unblinking.
      const options = ['up', 'left', 'right', 'down'];
      this.gazeTarget = LOOK[options[Math.floor(Math.random() * options.length)]];
      this.gazeUntil = t + rand(0.8, 1.5);
      this.glanceNext = t + rand(5, 9);
    }
    if (t > this.saccade.next) {
      this.saccade = {x: rand(-0.12, 0.12) * gl, y: rand(-0.09, 0.09) * gl, next: t + rand(0.7, 2.6)};
    }
    let [tx, ty] = this.thinking ? [-0.4, 0.8] : this.gazeTarget;
    if (this.follow) [tx, ty] = [0, 0];
    else if (!this.thinking && this.gazeTarget === LOOK.user) {
      // "Looking at the user" means at the face the camera sees; with nobody there, eyes drift off.
      if (this.userPos) [tx, ty] = [this.userPos.x, this.userPos.y];
      else if (this.absent) [tx, ty] = [0.3, -0.25];
    }
    this.gaze.x = approach(this.gaze.x, tx + this.saccade.x, 14, dt);
    this.gaze.y = approach(this.gaze.y, ty + this.saccade.y, 14, dt);
    add('ParamEyeBallX', this.gaze.x);
    add('ParamEyeBallY', this.gaze.y);
    // The head follows the eyes a little, as it does in life.
    add('ParamAngleX', this.gaze.x * 9);
    add('ParamAngleY', this.gaze.y * 7);
    add('ParamBodyAngleX', this.gaze.x * 3);
    if (this.thinking) { add('ParamAngleZ', -6); add('ParamBrowLY', 0.25); add('ParamBrowRY', 0.1); }

    // --- listening: attentive tilt, raised brows, small back-channel nods ---
    if (this.listening) {
      add('ParamAngleZ', 3);
      add('ParamBrowLY', 0.2);
      add('ParamBrowRY', 0.2);
      if (t > this.nodNext) { this.perform('nod'); this.nodNext = t + rand(2.5, 5); }
    }

    // --- speech: mouth opening and shape from the audio, head beats on emphasis ---
    const target = this.speaking ? clamp(this.level * 3.2, 0, 1) : 0;
    this.mouth = approach(this.mouth, target, target > this.mouth ? 28 : 14, dt);
    add('ParamMouthOpenY', this.mouth);
    this.levelSlow = approach(this.levelSlow, this.level, 5, dt);
    if (this.speaking) {
      // Wide vowels (i, e) vs round ones (o, u) change the mouth shape, not just its opening.
      this.vowelSmooth = approach(this.vowelSmooth, this.vowel, 12, dt);
      add('ParamMouthForm', this.vowelSmooth * this.mouth * 0.7);
      add('ParamAngleX', Math.sin(t * 2.3) * 2 * Math.min(1, this.mouth * 2) * L);
      // A sudden rise above the running average is a stressed syllable: punctuate it with a small head beat.
      if (this.level - this.levelSlow > 0.025 && t > this.beatNext) {
        this.gestures.push({type: 'beat', t0: t, dur: 0.4, dir: rand(-1, 1), amp: rand(0.6, 1)});
        this.beatNext = t + rand(0.45, 1.1);
      }
    } else this.vowelSmooth = approach(this.vowelSmooth, 0, 8, dt);

    // --- occasional brow flick: a tiny sign of life ---
    this.browFlick.next -= dt;
    if (this.browFlick.next <= 0 && this.browFlick.t < 0) this.browFlick.t = 0;
    if (this.browFlick.t >= 0) {
      this.browFlick.t += dt;
      const p = this.browFlick.t / 0.5;
      const w = Math.sin(clamp(p, 0, 1) * Math.PI);
      add('ParamBrowLY', 0.3 * w); add('ParamBrowRY', 0.3 * w);
      if (p >= 1) { this.browFlick.t = -1; this.browFlick.next = rand(6, 14); }
    }

    // --- gestures commanded by the net ---
    let winkClose = 0, pulse = 0, squint = 0;
    this.gestures = this.gestures.filter(g => (t - g.t0) < g.dur);
    for (const g of this.gestures) {
      const p = (t - g.t0) / g.dur, env = Math.sin(Math.PI * p);
      if (g.type === 'nod') add('ParamAngleY', -10 * gl * Math.sin(p * 4 * Math.PI) * (1 - p * 0.5));
      else if (g.type === 'shake') add('ParamAngleX', 11 * gl * Math.sin(p * 5 * Math.PI) * (1 - p));
      else if (g.type === 'tilt') { add('ParamAngleZ', 11 * gl * env * g.dir); add('ParamBrowLY', 0.25 * env); add('ParamBrowRY', 0.25 * env); }
      else if (g.type === 'wink') { winkClose = Math.max(winkClose, env); add('ParamAngleZ', 3 * env * g.dir); add('ParamMouthForm', 0.5 * env); }
      else if (g.type === 'lean') { pulse = Math.max(pulse, env); add('ParamAngleY', -3 * env); }
      // Whole-body gestures use only head, body, brows, mouth and cheeks, which most rigs share; ids a rig lacks are skipped.
      else if (g.type === 'shrug') {
        add('ParamAngleZ', 7 * gl * env * g.dir); add('ParamBodyAngleY', 5 * env); add('ParamAngleY', 3 * env);
        add('ParamMouthForm', -0.4 * env); add('ParamBrowLY', 0.4 * env); add('ParamBrowRY', 0.4 * env);
      } else if (g.type === 'bow') {
        add('ParamAngleY', -18 * gl * env); add('ParamBodyAngleY', -6 * gl * env); squint = Math.max(squint, 0.8 * env);
      } else if (g.type === 'giggle') {
        add('ParamAngleZ', 4 * gl * env * Math.sin(p * 10 * Math.PI)); add('ParamBodyAngleZ', 2 * gl * env * Math.sin(p * 10 * Math.PI + 1));
        add('ParamAngleY', -3 * gl * env * Math.abs(Math.sin(p * 10 * Math.PI))); add('ParamMouthForm', 0.8 * env); squint = Math.max(squint, 0.5 * env);
      } else if (g.type === 'puff') {
        for (const id of ['ParamCheekPuff', 'ParamCheekPuff2', 'CheekPuff']) add(id, env);
        add('ParamAngleZ', 5 * gl * env * g.dir); add('ParamBrowLY', -0.3 * env); add('ParamBrowRY', -0.3 * env);
      } else if (g.type === 'blush') add('ParamCheek', clamp(env * 2, 0, 1));
      else if (g.type === 'sigh') {
        add('ParamAngleY', -8 * gl * env); add('ParamBodyAngleY', -4 * gl * env); squint = Math.max(squint, 0.5 * env);
      } else if (g.type === 'bounce') {
        add('ParamBodyAngleY', 6 * gl * env * Math.abs(Math.sin(p * 6 * Math.PI))); add('ParamAngleY', 3 * gl * env * Math.sin(p * 6 * Math.PI));
        add('ParamMouthForm', 0.6 * env);
      } else if (g.type === 'beat') {
        add('ParamAngleY', -5 * gl * g.amp * env);
        add('ParamAngleZ', 3 * gl * g.dir * env);
        add('ParamBrowLY', 0.2 * g.amp * env); add('ParamBrowRY', 0.2 * g.amp * env);
      }
    }
    if (this.model) this.model.scale.set(this.baseScale * (1 + 0.04 * pulse));

    // --- dance: hops on every beat and a sway that turns every two beats ---
    let hop = 0, shift = 0;
    if (this.dancing) {
      const d = this.dancing, p = t - d.t0;
      if (p >= d.dur) this.dancing = null;
      else {
        const env = clamp(Math.min(p, d.dur - p) / 0.7, 0, 1), ph = p / d.period * Math.PI;
        const bounce = Math.abs(Math.sin(ph)), sway = Math.sin(ph / 2), {height: H, width: W} = this.app.screen;
        const big = d.style === 'hop';
        hop = bounce * H * (big ? 0.03 : 0.006) * env;
        shift = sway * W * (big ? 0.008 : 0.012) * env;
        add('ParamAngleZ', (big ? 6 : 9) * env * sway); add('ParamBodyAngleZ', (big ? 5 : 8) * env * sway); add('ParamBodyAngleX', 4 * env * sway);
        add('ParamAngleY', 3 * env * (1 - bounce)); add('ParamBodyAngleY', 3 * env * bounce);
        add('ParamMouthForm', 0.5 * env);
      }
    }
    if (this.model && this.basePos) this.model.position.set(this.basePos.x + shift, this.basePos.y - hop);

    // --- emotions: smoothly mix generic offsets and matching model expression files ---
    for (const name of Object.keys(EMOTION_PARAMS)) {
      const w = this.emotionMix[name] = approach(this.emotionMix[name] || 0, name === this.emotion ? 1 : 0, 6, dt);
      if (w < 0.01) continue;
      for (const [id, v] of Object.entries(EMOTION_PARAMS[name])) add(id, v * w);
    }
    const overrides = [];
    for (const ex of this.expressions) {
      const showing = Object.keys(this.fx).some(n => this.fx[n] > this.time && FX_KEYWORDS[n].test(exText(ex)));
      const wanted = showing || EXPRESSION_KEYWORDS[this.emotion]?.test(exText(ex)) ? 1 : 0;
      ex.weight = approach(ex.weight, wanted, 8, dt);
      if (ex.weight < 0.01) continue;
      for (const p of ex.params) {
        const base = this.def(p.Id);
        if (base === null) continue;
        if (p.Blend === 'Multiply') overrides.push([p.Id, base * (1 + ex.weight * (p.Value - 1))]);
        else if (p.Blend === 'Overwrite') overrides.push([p.Id, base + ex.weight * (p.Value - base)]);
        else add(p.Id, ex.weight * p.Value);
      }
    }
    for (const [id] of overrides) this.touched.add(id);

    // --- blink (faster when excited, slower when sad) ---
    this.blink.next -= dt;
    if (this.blink.next <= 0) this.triggerBlink();
    let closed = 0;
    if (this.blink.t >= 0) {
      this.blink.t += dt;
      closed = Math.sin(clamp(this.blink.t / 0.18, 0, 1) * Math.PI);
      if (this.blink.t > 0.18) {
        this.blink.t = -1;
        this.blink.next = this.blink.double ? 0.1 : rand(2, 6) / e;   // now and then, two blinks in a row
        this.blink.double = false;
      }
    }

    // Saved parameters persist between frames, so every id we ever touched is rewritten
    // each frame (back to its default when no offset applies), or it would stay stuck.
    for (const id of this.touched) if (!(id in offs)) offs[id] = 0;
    for (const id of ['ParamEyeLOpen', 'ParamEyeROpen']) if (!(id in offs)) offs[id] = 0;
    for (const [id, v] of Object.entries(offs)) {
      const base = this.def(id);
      if (base === null) continue;
      this.touched.add(id);
      this.core.setParameterValueById(id, base + v);
    }
    for (const [id, v] of overrides) this.core.setParameterValueById(id, v);
    if (this.motion) {   // the model's own movement, faded in and out
      const m = this.motion, el = t - m.t0;
      if (el >= m.dur) this.motion = null;
      else {
        const w = Math.min(1, el / 0.25, (m.dur - el) / 0.35);
        for (const c of m.curves) {
          if (this.def(c.Id) === null) continue;
          this.touched.add(c.Id);   // rewritten to its default once the movement is over
          const cur = this.core.getParameterValueById(c.Id);
          this.core.setParameterValueById(c.Id, cur + w * (curveValue(c.Segments, el) - cur));
        }
      }
    }
    for (const [id, close] of [['ParamEyeLOpen', Math.max(closed, winkClose, squint)], ['ParamEyeROpen', Math.max(closed, squint)]]) {
      if (close && this.def(id) !== null) this.core.setParameterValueById(id, this.core.getParameterValueById(id) * (1 - close));
    }
  }
}
window.Avatar = Avatar;
window.parseScript = parseScript;
