"""Her voice without the internet: the speech voices that Windows itself has (SAPI, the "Microsoft Irina/Zira/Haruka Desktop" kind).
Nothing is downloaded and no text leaves the computer. The price: the voices are plainer than the cloud ones, the pitch cannot be changed,
and each sentence starts a short PowerShell (about a second). Only the languages whose voice is installed in Windows can be spoken.

The text and the voice go to PowerShell through environment variables, never through the command line or a script built from them,
so no text can turn into a command. The voice name must be one that Windows listed."""
import os
import subprocess
import tempfile
import threading

from luna.core.script import CYRILLIC_RE, HANGUL_RE, JA_RE

TIMEOUT = 25
_LIST = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Speech; "
         "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
         "$s.GetInstalledVoices() | Where-Object {$_.Enabled} | ForEach-Object {$_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name}")
_SAY = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice($env:LUNA_VOICE); $s.Rate=[int]$env:LUNA_RATE; $s.Volume=[int]$env:LUNA_VOL; "
        "$s.SetOutputToWaveFile($env:LUNA_OUT); "
        "$s.Speak([IO.File]::ReadAllText($env:LUNA_IN,[Text.Encoding]::UTF8)); $s.Dispose()")
_cache = {}
_lock = threading.Lock()


class LocalVoiceError(Exception):
    """str(exc) is a short code: windows (not Windows), novoice (no installed voice for this language), fail."""


def _powershell(script, env=None, timeout=TIMEOUT):
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    cmd = ['powershell', '-NoProfile', '-NonInteractive', '-Command', script]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags, env=dict(os.environ, **(env or {})))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalVoiceError('fail') from exc
    if done.returncode:
        raise LocalVoiceError('fail')
    return done.stdout.decode('utf-8', errors='replace')


def voices(refresh=False):
    """[{'name', 'culture'}] of the voices Windows has; [] elsewhere."""
    if os.name != 'nt':
        return []
    with _lock:
        if refresh or 'voices' not in _cache:
            try:
                lines = _powershell(_LIST).splitlines()
            except LocalVoiceError:
                lines = []
            _cache['voices'] = [{'name': n.strip(), 'culture': c.strip()} for n, _, c in (ln.partition('|') for ln in lines) if n.strip() and c.strip()]
        return list(_cache['voices'])


def language_of(text):
    if JA_RE.search(text):
        return 'ja'
    if HANGUL_RE.search(text):
        return 'ko'
    if CYRILLIC_RE.search(text):
        return 'ru'
    return 'en'


def pick(text, available=None):
    """The installed voice for the language of the text, or None."""
    lang = language_of(text)
    for v in voices() if available is None else available:
        if v['culture'].lower().startswith(lang):
            return v['name']
    return None


def sapi_rate(percent):
    """The page's rate in percent (-50..+50 and the like) -> SAPI's -10..10."""
    return max(-10, min(10, round(percent / 10)))


def synthesize(text, rate=0, volume=0, available=None):
    """-> WAV bytes. LocalVoiceError when this is not Windows, no voice fits the language, or the speech failed."""
    if os.name != 'nt':
        raise LocalVoiceError('windows')
    name = pick(text, available)
    if not name:
        raise LocalVoiceError('novoice')
    with tempfile.TemporaryDirectory(prefix='luna-tts-') as folder:
        src, out = os.path.join(folder, 'in.txt'), os.path.join(folder, 'out.wav')
        with open(src, 'w', encoding='utf-8') as f:
            f.write(text)
        _powershell(_SAY, {'LUNA_VOICE': name, 'LUNA_RATE': str(sapi_rate(rate)), 'LUNA_VOL': str(max(0, min(100, 100 + int(volume)))), 'LUNA_IN': src, 'LUNA_OUT': out})
        try:
            with open(out, 'rb') as f:
                audio = f.read()
        except OSError as exc:
            raise LocalVoiceError('fail') from exc
    if not audio:
        raise LocalVoiceError('fail')
    return audio
