"""The real server refuses foreign Host / Origin headers (DNS rebinding) and sends the security headers."""
import http.client
import threading
from http.server import ThreadingHTTPServer

import pytest

import app


@pytest.fixture(scope='module')
def server():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=10)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    hdrs = {'Host': '127.0.0.1:%d' % srv.server_port}
    hdrs.update(headers or {})
    for k, v in hdrs.items():
        conn.putheader(k, v)
    data = body or b''
    conn.putheader('Content-Length', str(len(data)))
    conn.endheaders(data)
    r = conn.getresponse()
    out = (r.status, dict((k.lower(), v) for k, v in r.getheaders()), r.read())
    conn.close()
    return out


def test_own_page_is_served_with_headers(server):
    status, hdr, body = call(server, 'GET', '/')
    assert status == 200 and app.TOKEN.encode() in body
    assert 'content-security-policy' in hdr and hdr['x-frame-options'] == 'DENY' and hdr['referrer-policy'] == 'no-referrer'


def test_rebinding_host_is_refused_and_token_not_leaked(server):
    status, _, body = call(server, 'GET', '/', {'Host': 'evil.example:%d' % server.server_port})
    assert status == 403 and app.TOKEN.encode() not in body


def test_foreign_origin_is_refused(server):
    status, _, _ = call(server, 'POST', '/reset', {'Origin': 'http://evil.example', 'X-App-Token': app.TOKEN})
    assert status == 403


def test_wrong_token_is_refused(server):
    assert call(server, 'POST', '/reset', {'X-App-Token': 'nope'})[0] == 403


def test_json_responses_carry_headers(server):
    _, hdr, _ = call(server, 'GET', '/api/models')
    assert hdr['x-content-type-options'] == 'nosniff' and 'content-security-policy' not in hdr
