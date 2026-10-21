"""A foreign cookie the stdlib parser chokes on must not hide our session.

On localhost every port shares one cookie jar. Google Sign-In's g_state
cookie holds raw JSON; http.cookies.SimpleCookie stops at it and silently
drops the sid and auth_token that follow, so each request became a new,
logged-out session (login "did nothing" and the chat history vanished)."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import web
from ami.auth import generate_token

FOREIGN = '_ga=GA1.1.1; g_state={"i_l":0,"i_ll":1792620320000}'


@pytest.fixture
def url(monkeypatch):
    monkeypatch.setattr(web.answer_cache, "answer", lambda *a: ("ok", False))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get_state(url, cookie):
    req = urllib.request.Request(url + "/state", headers={"Cookie": cookie})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read()), r.headers.get_all("Set-Cookie") or []


def test_session_survives_a_json_cookie_before_it(url):
    _, set_cookies = _get_state(url, FOREIGN)
    sid = next(c.split(";")[0] for c in set_cookies if c.startswith("sid="))
    _, again = _get_state(url, f"{FOREIGN}; {sid}")
    assert not any(c.startswith("sid=") for c in again)      # same session, no new one minted


def test_login_survives_a_json_cookie_before_it(url):
    token = generate_token("demo1@cofy.ai", secret_key=web.SECRET_KEY)
    d, _ = _get_state(url, f"{FOREIGN}; auth_token={token}")
    assert d["user"] == "demo1@cofy.ai"
