import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

from security.auth import (
    SCOPE_METRICS,
    SCOPE_SESSION,
    derive_web_user_id,
    issue_token,
    verify_login_widget,
    verify_token,
    verify_webapp_init_data,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]


def test_token_roundtrip():
    assert verify_token(issue_token(42)) == 42


def test_tampered_token_rejected():
    token = issue_token(42)
    body, sig = token.split(".")
    forged_body = issue_token(43).split(".")[0]
    assert verify_token(f"{forged_body}.{sig}") is None
    assert verify_token(token[:-2] + "xx") is None
    assert verify_token("garbage") is None
    assert verify_token("") is None


def test_expired_token_rejected():
    assert verify_token(issue_token(42, ttl=-1)) is None


def test_metrics_token_cannot_be_used_as_session():
    token = issue_token(42, scope=SCOPE_METRICS, ttl=None)
    assert verify_token(token) is None
    assert verify_token(token, (SCOPE_SESSION, SCOPE_METRICS)) == 42


def _signed_init_data(user: dict, auth_date: int) -> str:
    fields = {"auth_date": str(auth_date), "query_id": "AAH", "user": json.dumps(user)}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_webapp_init_data_valid():
    init = _signed_init_data({"id": 777, "first_name": "A"}, int(time.time()))
    assert verify_webapp_init_data(init)["id"] == 777


def test_webapp_init_data_forged_user_rejected():
    init = _signed_init_data({"id": 777}, int(time.time()))
    forged = init.replace("777", "778")
    assert verify_webapp_init_data(forged) is None


def test_webapp_init_data_too_old_rejected():
    init = _signed_init_data({"id": 777}, int(time.time()) - 3 * 86400)
    assert verify_webapp_init_data(init) is None


def test_login_widget():
    data = {"id": 555, "first_name": "B", "auth_date": int(time.time())}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    data["hash"] = hmac.new(
        hashlib.sha256(BOT_TOKEN.encode()).digest(), check.encode(), hashlib.sha256
    ).hexdigest()
    assert verify_login_widget(dict(data))["id"] == 555
    assert verify_login_widget({**data, "id": 556}) is None


def test_derive_web_user_id_matches_frontend_formula():
    uid = derive_web_user_id("2b1c1c3e-0000-4000-8000-000000000000")
    assert 5_000_000_000 <= uid < 10_000_000_000
    assert uid == derive_web_user_id("2b1c1c3e-0000-4000-8000-000000000000")
