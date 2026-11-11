/* Luna's eyes: the webcam is read by MediaPipe Face Landmarker inside the browser. Nothing is recorded or
   uploaded; only the face position and a couple of expression scores leave this file, as small events. */
const MP_VERSION = '0.10.14';
const MP_BASE = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@' + MP_VERSION;
const MP_MODEL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

const MP_SOURCES = [{base: '/web/vendor/mediapipe', model: '/web/vendor/mediapipe/face_landmarker.task'}, {base: MP_BASE, model: MP_MODEL}];

class Vision {
  /* hooks: {onSmile(), onSurprise(), onReturn(), onLeave()} */
  constructor(avatar, video, hooks = {}) {
    this.avatar = avatar;
    this.video = video;
    this.hooks = hooks;
    this.active = false;
    this.present = false;
    this.seenAt = 0;        // last time a face was in view
    this.absentSince = 0;
    this.smileSince = 0;
    this.lastSmile = 0;
    this.lastSurprise = 0;
    this.timer = null;
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({video: {width: 320, height: 240, facingMode: 'user'}});
    this.video.srcObject = this.stream;
    await this.video.play();
    let failure = null;
    for (const src of MP_SOURCES) {   // the copy on this computer first (tools/fetch_vendor.py), then the internet
      try {
        const mp = await import(src.base + '/vision_bundle.mjs');
        const files = await mp.FilesetResolver.forVisionTasks(src.base + '/wasm');
        this.landmarker = await mp.FaceLandmarker.createFromOptions(files, {
          baseOptions: {modelAssetPath: src.model}, runningMode: 'VIDEO', numFaces: 1, outputFaceBlendshapes: true});
        failure = null;
        break;
      } catch (e) { failure = e; }
    }
    if (failure) {
      this.stop();
      throw Error(t('cam.model') + (failure.message || failure));
    }
    this.active = true;
    this.seenAt = performance.now();
    this.present = true;
    this.timer = setInterval(() => this.tick(), 100);
  }

  stop() {
    clearInterval(this.timer);
    this.active = false;
    this.stream?.getTracks().forEach(t => t.stop());
    this.video.srcObject = null;
    this.landmarker?.close?.();
    this.landmarker = null;
    this.avatar.userPos = null;
    this.avatar.absent = false;
  }

  tick() {
    if (!this.landmarker || this.video.readyState < 2) return;
    try { this.handle(this.landmarker.detectForVideo(this.video, performance.now())); } catch { /* skip a bad frame */ }
  }

  /* One detection result -> avatar gaze, presence and reactions. Kept separate from the camera so it can be fed directly. */
  handle(result, now = performance.now()) {
    const face = result.faceLandmarks && result.faceLandmarks[0];
    if (!face) {
      if (this.present && now - this.seenAt > 4000) {   // gone for a few seconds: nobody is there
        this.present = false;
        this.absentSince = now;
        this.avatar.userPos = null;
        this.avatar.absent = true;
        this.hooks.onLeave?.();
      }
      return;
    }
    this.seenAt = now;
    if (!this.present) {
      this.present = true;
      this.avatar.absent = false;
      if (now - this.absentSince > 30000) this.hooks.onReturn?.();
    }
    // Where is the face? The camera sees you mirrored, so image-left is your right = the screen's right.
    const nose = face[1];
    const target = {x: clamp((0.5 - nose.x) * 1.6, -0.8, 0.8), y: clamp((0.5 - nose.y) * 1.2, -0.5, 0.5)};
    const p = this.avatar.userPos || target;
    this.avatar.userPos = {x: p.x + (target.x - p.x) * 0.3, y: p.y + (target.y - p.y) * 0.3};

    const scores = {};
    for (const c of (result.faceBlendshapes?.[0]?.categories || [])) scores[c.categoryName] = c.score;
    const smile = ((scores.mouthSmileLeft || 0) + (scores.mouthSmileRight || 0)) / 2;
    if (smile > 0.5) {
      this.smileSince = this.smileSince || now;
      if (now - this.smileSince > 600 && now - this.lastSmile > 8000) { this.lastSmile = now; this.hooks.onSmile?.(); }
    } else this.smileSince = 0;
    if ((scores.jawOpen || 0) > 0.5 && (scores.browInnerUp || 0) > 0.5 && now - this.lastSurprise > 8000) {
      this.lastSurprise = now;
      this.hooks.onSurprise?.();
    }
  }
}
window.Vision = Vision;
