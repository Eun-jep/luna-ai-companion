"""Updating the program from an update feed that the creator chose. Nothing happens on its own beyond asking the feed whether a newer version exists.

The feed (`"update_feed": "https://.../luna.json"` in settings.json; empty = no updates, no network) is a small JSON file:
    {"version": "0.9.1", "url": "luna-0.9.1.zip", "sha256": "<64 hex>", "notes": "what changed"}        (url may be relative to the feed)
Rules, each one enforced here and tested:
  - https only (http only for this computer, for tests); a redirect must obey the same rule; the request carries nothing about the user;
  - the package is downloaded only after the creator presses Install, with a size cap, and its SHA-256 must equal the feed's;
  - the version must be newer than the running one, and the same version must be written inside the package (luna/__init__.py);
  - only program files are replaced (never settings.json, actions.json, models, web/vendor, user data in %APPDATA%\\Luna); no path may leave the program folder;
  - every .py file must compile before the first file is touched; each replaced file is backed up first; any failure restores the backup;
  - rollback() puts the previous version back.
The program must be restarted afterwards. Pure standard library.

What it cannot do: tell a good package from a bad one when the feed itself is hostile. The SHA-256 comes from the same feed, so it protects against damage and
mix-ups, not against whoever controls the feed (there is no signature: the standard library has no public-key verification). Choose a feed you trust."""
import hashlib
import ipaddress
import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile

from luna import paths

FEED_MAX = 64_000
PACKAGE_MAX = 200 << 20
TIMEOUT = 20
TTL = 3600   # a checked update can be installed for an hour
# what an update may replace: program code only
ALLOWED = ('app.py', 'index.html', 'requirements.txt', 'requirements-dev.txt', 'requirements.lock', 'README.md', 'CHANGELOG.md', 'pyproject.toml',
           'luna/', 'web/', 'tools/', 'desktop/', 'docs/')
NEVER = ('web/vendor/', 'desktop/node_modules/', 'settings.json', 'actions.json')
VERSION_RE = re.compile(r'\d{1,4}(\.\d{1,4}){1,3}')
_CHECKED = {}   # the manifest that was checked and may be installed: {'manifest', 'at'}


class UpdateError(Exception):
    """str(exc) is a short code: feed, nofeed, net, bad, size, hash, version, unsafe, syntax, nothing, busy, write."""


def current_version():
    from luna import __version__
    return __version__


def parse_version(text):
    if not isinstance(text, str) or not VERSION_RE.fullmatch(text):
        raise UpdateError('bad')
    return tuple(int(x) for x in text.split('.'))


def feed_url():
    from luna.core.config import CONFIG
    url = CONFIG.get('update_feed')
    return url.strip() if isinstance(url, str) and url.strip() else ''


def url_ok(url):
    """https anywhere, plain http only to this computer."""
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme == 'https' and parts.hostname:
            return True
        if parts.scheme == 'http' and parts.hostname:
            return parts.hostname == 'localhost' or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        pass
    return False


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_ok(newurl):
            raise UpdateError('feed')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url):
    if not url_ok(url):
        raise UpdateError('feed')
    opener = urllib.request.build_opener(_Redirects)
    request = urllib.request.Request(url, headers={'User-Agent': 'luna-updater'})   # nothing about the user or the computer
    try:
        return opener.open(request, timeout=TIMEOUT)
    except UpdateError:
        raise
    except Exception as exc:   # network, DNS, HTTP status
        raise UpdateError('net') from exc


def check(url=None):
    """Ask the feed -> {'current', 'available', 'version', 'notes'}. Remembers the offer for install()."""
    url = url or feed_url()
    if not url:
        raise UpdateError('nofeed')
    with _open(url) as resp:
        raw = resp.read(FEED_MAX + 1)
    if len(raw) > FEED_MAX:
        raise UpdateError('bad')
    try:
        data = json.loads(raw.decode('utf-8'))
        version, sha = data['version'], str(data['sha256']).lower()
        package = urllib.parse.urljoin(url, str(data['url']))
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise UpdateError('bad') from exc
    if not re.fullmatch(r'[0-9a-f]{64}', sha) or not url_ok(package):
        raise UpdateError('bad')
    newer = parse_version(version) > parse_version(current_version())
    notes = ' '.join(str(data.get('notes', '')).split())[:600]
    _CHECKED.clear()
    if newer:
        _CHECKED.update(manifest={'version': version, 'url': package, 'sha256': sha}, at=time.time())
    return {'current': current_version(), 'available': newer, 'version': version, 'notes': notes}


def safe_member(name):
    """-> the relative path with forward slashes when the package may write it, else None."""
    name = name.replace('\\', '/')
    if not name or name.endswith('/') or name.startswith('/') or re.match(r'^[A-Za-z]:', name) or '\x00' in name:
        return None
    if any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in name.split('/')):
        return None
    if name.startswith(NEVER) or name in NEVER or not (name in ALLOWED or name.startswith(tuple(a for a in ALLOWED if a.endswith('/')))):
        return None
    return name


def _download(manifest, target):
    digest, size = hashlib.sha256(), 0
    with _open(manifest['url']) as resp, open(target, 'wb') as out:
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            size += len(block)
            if size > PACKAGE_MAX:
                raise UpdateError('size')
            digest.update(block)
            out.write(block)
    if digest.hexdigest() != manifest['sha256']:
        raise UpdateError('hash')


def _plan(package, version):
    """Validate the whole package before anything is written -> [(member name, relative path)]."""
    try:
        zf = zipfile.ZipFile(package)
    except zipfile.BadZipFile as exc:
        raise UpdateError('bad') from exc
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        plan = []
        for info in infos:
            rel = safe_member(info.filename)
            if rel is None:
                raise UpdateError('unsafe')
            if info.file_size > PACKAGE_MAX:
                raise UpdateError('size')
            plan.append((info.filename, rel))
        if not plan or sum(i.file_size for i in infos) > 4 * PACKAGE_MAX:
            raise UpdateError('size' if plan else 'nothing')
        names = dict(plan)
        inner = None
        if 'luna/__init__.py' in names.values():
            member = next(m for m, r in plan if r == 'luna/__init__.py')
            match = re.search(r"__version__\s*=\s*['\"]([\d.]+)['\"]", zf.read(member).decode('utf-8', errors='replace'))
            inner = match.group(1) if match else None
        if inner != version:
            raise UpdateError('version')   # a relabelled old package is not a new version
        for member, rel in plan:
            if rel.endswith('.py'):
                try:
                    compile(zf.read(member), rel, 'exec')
                except (SyntaxError, ValueError) as exc:
                    raise UpdateError('syntax') from exc
    return plan


def _backup_dir(version):
    return paths.DATA_DIR / 'update_backup' / version


def _restore(backup):
    """Put the backed-up files back and delete the files the update added."""
    log = json.loads((backup / 'log.json').read_text(encoding='utf-8'))
    for rel in log['replaced']:
        target = paths.ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / 'files' / rel, target)
    for rel in log['added']:
        try:
            (paths.ROOT / rel).unlink()
        except OSError:
            pass
    return log['version']


def install():
    """Download, verify and apply the update that check() offered -> {'version', 'files', 'restart': True}."""
    offer = _CHECKED.get('manifest')
    if not offer or time.time() - _CHECKED.get('at', 0) > TTL:
        raise UpdateError('nothing')
    version = offer['version']
    if parse_version(version) <= parse_version(current_version()):
        raise UpdateError('version')
    staging = paths.DATA_DIR / 'updates'
    staging.mkdir(parents=True, exist_ok=True)
    package = staging / ('luna-%s.zip' % version)
    try:
        _download(offer, package)
        plan = _plan(package, version)
        backup = _backup_dir(current_version())
        if backup.exists():
            shutil.rmtree(backup)
        (backup / 'files').mkdir(parents=True)
        replaced, added = [], []
        log = {'version': current_version(), 'replaced': replaced, 'added': added}
        try:
            with zipfile.ZipFile(package) as zf:
                for member, rel in plan:
                    target = paths.ROOT / rel
                    if target.is_file():
                        keep = backup / 'files' / rel
                        keep.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, keep)
                        replaced.append(rel)
                    else:
                        added.append(rel)
                    (backup / 'log.json').write_text(json.dumps(log), encoding='utf-8')   # kept up to date: a crash half-way can still be undone
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tmp = target.with_name(target.name + '.new')
                    tmp.write_bytes(zf.read(member))
                    os.replace(tmp, target)
        except (OSError, zipfile.BadZipFile) as exc:
            _restore(backup)
            raise UpdateError('write') from exc
        for old in sorted((paths.DATA_DIR / 'update_backup').iterdir(), key=lambda p: p.stat().st_mtime)[:-2]:
            shutil.rmtree(old, ignore_errors=True)   # keep the last two
        _CHECKED.clear()
        return {'version': version, 'files': len(plan), 'restart': True}
    finally:
        try:
            package.unlink()
        except OSError:
            pass


def rollback():
    """Put the previous version back -> {'version', 'restart': True}."""
    base = paths.DATA_DIR / 'update_backup'
    backups = sorted((p for p in base.iterdir() if (p / 'log.json').is_file()), key=lambda p: p.stat().st_mtime) if base.is_dir() else []
    if not backups:
        raise UpdateError('nothing')
    version = _restore(backups[-1])
    shutil.rmtree(backups[-1], ignore_errors=True)
    return {'version': version, 'restart': True}


def has_backup():
    base = paths.DATA_DIR / 'update_backup'
    return base.is_dir() and any((p / 'log.json').is_file() for p in base.iterdir())


