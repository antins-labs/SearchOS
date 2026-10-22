"""CI-only HTTPS smoke test. localhost uses Caddy's local CA, never real API keys."""
import http.cookiejar
import json
import ssl
import subprocess
import urllib.error
import urllib.request

COMPOSE = ["docker", "compose", "--env-file", "deploy/.env", "-f", "deploy/compose.yaml"]
ORIGIN = "https://localhost"


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )


def request(opener, path, body=None):
    headers = {"Origin": ORIGIN, "X-SearchOS-Request": "1", "Content-Type": "application/json"}
    req = urllib.request.Request(ORIGIN + path, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with opener.open(req, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main():
    anonymous, admin, phone = client(), client(), client()
    assert request(anonymous, "/m")[0] == 200
    assert request(anonymous, "/api/health")[0] == 200
    assert request(anonymous, "/api/history")[0] == 401
    token = subprocess.check_output(
        COMPOSE + ["exec", "-T", "api", "cat", "/data/assistant/admin-token"], text=True).strip()
    status, _ = request(admin, "/api/assistant/login", {"token": token, "name": "CI admin"})
    assert status == 200
    status, raw = request(admin, "/api/assistant/pairings", {})
    assert status == 200
    code = json.loads(raw)["code"]
    assert request(phone, "/api/assistant/pairings/claim", {"code": code, "name": "CI phone"})[0] == 200
    assert request(anonymous, "/api/assistant/pairings/claim", {"code": code})[0] != 200
    subprocess.run(COMPOSE + ["restart", "api"], check=True)
    subprocess.run(COMPOSE + ["up", "-d", "--wait", "--wait-timeout", "180"], check=True)
    status, raw = request(phone, "/api/assistant/access")
    assert status == 200 and json.loads(raw)["authenticated"]
    print("HTTPS page, protected API, admin login, single-use pairing and restart persistence passed.")


if __name__ == "__main__":
    main()
