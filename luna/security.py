"""Small, dependency-free security helpers for the local server and for text that does not come from the creator.

1. Who may talk to the server. It listens on 127.0.0.1 only, but a web page on the internet can still reach it through the user's own browser
   (DNS rebinding: attacker.example resolves to 127.0.0.1 and the page then reads "/" and the token inside it). So every request must carry a
   Host that is exactly our own address, and an Origin (when the browser sends one) that is our own page. The token is compared in constant time.
2. Safe response headers (no framing, no referrer, no content sniffing, own-origin resources only).
3. Text from outside (web pages, documents, code files, the clipboard): neutralize() makes sure it can never close the "data" frame it is shown
   in, or imitate one of her own commands.
"""
import hmac
import re
import secrets

LOOPBACK = ('127.0.0.1', 'localhost', '[::1]')


def allowed_hosts(port):
    """Host header values that are really us."""
    return {'%s:%d' % (h, port) for h in LOOPBACK}


def host_ok(host, port):
    """The Host header must be one of our own loopback names with our port (this is what stops DNS rebinding)."""
    return isinstance(host, str) and host.strip().lower() in allowed_hosts(port)


def origin_ok(origin, port):
    """No Origin (same-origin GET, a non-browser client such as Electron's main process) is fine. When a browser sends one it must be our own."""
    if origin in (None, ''):
        return True
    return isinstance(origin, str) and origin.strip().lower() in {'http://' + h for h in allowed_hosts(port)}


def token_ok(supplied, token):
    """Constant-time comparison of the session token (never `==`: timing)."""
    if not isinstance(supplied, str) or not isinstance(token, str) or not token:
        return False
    return hmac.compare_digest(supplied.encode('utf-8', 'replace'), token.encode('utf-8'))


# Everything the page itself needs: its own scripts, the CDN fallbacks it names, blobs and data: for audio, images and the avatar.
# No 'unsafe-inline': the one inline script of a page carries a fresh nonce for that response; styles are set from scripts (allowed) or style.css.
_CSP = ("default-src 'self'; "
        "script-src 'self' 'nonce-{nonce}' 'wasm-unsafe-eval' blob: https://cdnjs.cloudflare.com https://cubism.live2d.com https://cdn.jsdelivr.net; "
        "style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob: data:; "
        "connect-src 'self' https://cdn.jsdelivr.net https://storage.googleapis.com data: blob:; worker-src 'self' blob:; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def new_nonce():
    return secrets.token_urlsafe(16)


def csp(nonce):
    return _CSP.replace('{nonce}', nonce)


HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(self), microphone=(self), geolocation=()',
}


def page_headers(nonce):
    """Headers for the HTML pages (they also get the content-security policy, with this response's nonce)."""
    return dict(HEADERS, **{'Content-Security-Policy': csp(nonce)})


# --- text from outside -------------------------------------------------------------------------------------------------------------------
_FRAME = re.compile(r'<<<+|>>>+')                # the markers around "this is data" blocks
_FENCE = re.compile(r'`{3,}')                    # a code fence would end a ``` block
_OPEN = re.compile(r'<\s*/?\s*(?:system|assistant|user|instructions?|tool)[^>]*>', re.I)   # fake role / instruction tags


def neutralize(text, limit=None):
    """Make a piece of outside text harmless to put inside a frame like  <<< ... >>>  or ``` ... ```: the frame markers, code fences and fake
    role tags are broken up (still readable), control characters are dropped. It does not judge what the text SAYS: the program, not the text,
    decides what may happen (nothing opens, runs or is sent on its own after outside text; see app.py `tainted`)."""
    text = '' if text is None else str(text)
    text = ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)
    text = _FRAME.sub(lambda m: '​'.join(m.group(0)), text)   # every character of the run is separated: no three in a row are left
    text = _FENCE.sub(lambda m: "'" * len(m.group(0)), text)
    text = _OPEN.sub(lambda m: m.group(0).replace('<', '‹').replace('>', '›'), text)
    return text[:limit] if limit else text
