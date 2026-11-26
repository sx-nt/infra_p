"""Teste de fumaça do ambiente implantado (usado pelo CD após o `pulumi up`).

Uso: CLASSLY_URL=$(pulumi stack output url) uv run pytest tests/deployed
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import pytest

BASE_URL = os.environ.get("CLASSLY_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="Defina CLASSLY_URL com a URL do ambiente implantado.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def get(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with _opener.open(request, timeout=20) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode()


def test_site_is_served_over_https():
    status, headers, body = get(f"{BASE_URL}/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert '<div id="root">' in body

    asset = re.search(r'src="(/assets/[^"]+\.js)"', body).group(1)
    status, headers, _ = get(f"{BASE_URL}{asset}")
    assert status == 200 and "javascript" in headers["Content-Type"]
    assert "immutable" in headers["Cache-Control"]


def test_http_redirects_to_https():
    status, headers, _ = get(BASE_URL.replace("https://", "http://", 1) + "/")
    assert status in (301, 302) and headers["Location"].startswith("https://")


def test_api_health_is_public():
    status, _, body = get(f"{BASE_URL}/api/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok", "service": "classly-api"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer token-invalido"}])
def test_api_requires_valid_token(headers):
    status, _, _ = get(f"{BASE_URL}/api/teachers", headers)
    assert status == 401


def test_login_page_accepts_the_published_client():
    status, _, body = get(f"{BASE_URL}/config.json")
    assert status == 200
    auth = json.loads(body)["auth"]
    assert auth["redirectUri"] == f"{BASE_URL}/"
    query = urllib.parse.urlencode({
        "response_type": "code", "client_id": auth["clientId"], "redirect_uri": auth["redirectUri"],
        "scope": "openid email profile", "code_challenge": "x" * 43, "code_challenge_method": "S256",
    })
    status, headers, _ = get(f"{auth['domain']}/oauth2/authorize?{query}")
    # O Cognito só redireciona para a tela de login se cliente e callback forem válidos.
    assert status == 302
    assert "/login" in headers["Location"] and "error" not in headers["Location"]
