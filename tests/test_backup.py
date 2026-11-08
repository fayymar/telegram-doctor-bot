"""Резервные копии: шифрование, подпись запросов к R2, хранение 30 дней."""
import asyncio
import gzip
import json
from datetime import datetime, timedelta, timezone

import pytest

from services import backup
from services.backup_crypto import decrypt, encrypt, generate_keypair, is_valid_public_key


def test_encrypt_roundtrip_and_wrong_key():
    private, public = generate_keypair()
    blob = encrypt(b"secret health data", public)
    assert b"secret" not in blob
    assert decrypt(blob, private) == b"secret health data"
    other_private, _ = generate_keypair()
    with pytest.raises(Exception):
        decrypt(blob, other_private)


def test_tampered_backup_rejected():
    private, public = generate_keypair()
    blob = bytearray(encrypt(b"data", public))
    blob[-1] ^= 1
    with pytest.raises(Exception):
        decrypt(bytes(blob), private)
    with pytest.raises(ValueError):
        decrypt(b"garbage", private)


def test_public_key_validation():
    _, public = generate_keypair()
    assert is_valid_public_key(public)
    assert not is_valid_public_key("not-a-key")
    assert not is_valid_public_key("")


@pytest.mark.parametrize("method,url,body", [
    ("PUT", "https://acc.eu.r2.cloudflarestorage.com/bucket/backups/2026-11-08T03-00-00Z.json.gz.enc", b"x" * 10),
    ("GET", "https://acc.eu.r2.cloudflarestorage.com/bucket?continuation-token=a%2Fb%3D&list-type=2&prefix=backups%2F", b""),
    ("DELETE", "https://acc.eu.r2.cloudflarestorage.com/bucket/backups/old.json.gz.enc", b""),
])
def test_sigv4_matches_botocore(monkeypatch, method, url, body):
    import hashlib

    from botocore.auth import S3SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    now = datetime(2026, 11, 8, 3, 0, 0, tzinfo=timezone.utc)
    payload_hash = hashlib.sha256(body).hexdigest()
    ours = backup.sign_request(method, url, payload_hash, "AKID", "SECRET", now)

    import botocore.auth as auth_mod

    class FixedDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return now.replace(tzinfo=None)

        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(auth_mod.datetime, "datetime", FixedDatetime)
    req = AWSRequest(method=method, url=url, data=body,
                     headers={"x-amz-content-sha256": payload_hash})
    S3SigV4Auth(Credentials("AKID", "SECRET"), "s3", "auto").add_auth(req)
    assert req.headers["X-Amz-Date"] == ours["x-amz-date"]
    assert req.headers["Authorization"] == ours["Authorization"]


def test_key_time():
    assert backup._key_time("backups/2026-11-08T03-04-05Z.json.gz.enc") == datetime(
        2026, 11, 8, 3, 4, 5, tzinfo=timezone.utc)
    assert backup._key_time("backups/other-file.txt") is None


class FakeR2:
    def __init__(self, keys=()):
        self.objects = {k: b"" for k in keys}

    async def put(self, key, body):
        self.objects[key] = body

    async def delete(self, key):
        del self.objects[key]

    async def list(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]


def _fake_dump(monkeypatch, rows):
    async def fake_dump_table(table, pk):
        return rows.get(table, [])

    async def fake_dump_auth():
        return [{"id": "u1", "email": "a@b.c"}]

    monkeypatch.setattr(backup, "_dump_table", fake_dump_table)
    monkeypatch.setattr(backup, "_dump_auth_users", fake_dump_auth)


def test_run_backup_uploads_encrypted_and_prunes_old(monkeypatch):
    private, public = generate_keypair()
    _fake_dump(monkeypatch, {"user_profiles": [{"user_id": 1, "name": "Иван"}]})
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H-%M-%SZ"
    old = f"backups/{(now - timedelta(days=31)).strftime(fmt)}.json.gz.enc"
    recent = f"backups/{(now - timedelta(days=29)).strftime(fmt)}.json.gz.enc"
    r2 = FakeR2([old, recent, "backups/unrelated.txt"])
    cfg = {"public_key": public, "keep_days": 30}

    key = asyncio.run(backup.run_backup(cfg, r2))

    assert old not in r2.objects
    assert recent in r2.objects and "backups/unrelated.txt" in r2.objects
    data = json.loads(gzip.decompress(decrypt(r2.objects[key], private)))
    assert data["tables"]["user_profiles"] == [{"user_id": 1, "name": "Иван"}]
    assert data["tables"]["consultations"] == []
    assert data["auth_users"] == [{"id": "u1", "email": "a@b.c"}]
    assert set(data["tables"]) == set(backup.BACKUP_TABLES)


def test_failed_upload_keeps_old_backups(monkeypatch):
    _, public = generate_keypair()
    _fake_dump(monkeypatch, {})
    old = "backups/2000-01-01T00-00-00Z.json.gz.enc"

    class FailingR2(FakeR2):
        async def put(self, key, body):
            raise RuntimeError("R2 PUT failed: HTTP 500")

    r2 = FailingR2([old])
    with pytest.raises(RuntimeError):
        asyncio.run(backup.run_backup({"public_key": public, "keep_days": 30}, r2))
    assert old in r2.objects


def test_dump_table_pages(monkeypatch):
    monkeypatch.setattr(backup, "_PAGE", 2)
    pages = [[{"id": 1}, {"id": 2}], [{"id": 3}], []]

    async def fake_run_query(func, *a, **kw):
        return type("R", (), {"data": pages.pop(0)})()

    monkeypatch.setattr(backup, "run_query", fake_run_query)
    assert asyncio.run(backup._dump_table("consents", "id")) == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_r2_list_parses_pages(monkeypatch):
    ns = 'xmlns="http://s3.amazonaws.com/doc/2006-03-01/"'
    responses = [
        f"<ListBucketResult {ns}><IsTruncated>true</IsTruncated><NextContinuationToken>t1</NextContinuationToken>"
        f"<Contents><Key>backups/a</Key></Contents><Contents><Key>backups/b</Key></Contents></ListBucketResult>",
        f"<ListBucketResult {ns}><IsTruncated>false</IsTruncated>"
        f"<Contents><Key>backups/c</Key></Contents></ListBucketResult>",
    ]
    queries = []

    async def fake_request(self, method, path="", query="", body=b""):
        queries.append(query)
        return responses.pop(0).encode()

    monkeypatch.setattr(backup.R2, "_request", fake_request)
    r2 = backup.R2("https://acc.eu.r2.cloudflarestorage.com", "bucket", "k", "s")
    assert asyncio.run(r2.list("backups/")) == ["backups/a", "backups/b", "backups/c"]
    assert "continuation-token=t1" in queries[1]


def test_config_requires_all_settings(monkeypatch):
    _, public = generate_keypair()
    env = {"R2_ENDPOINT": "https://acc.eu.r2.cloudflarestorage.com", "R2_BUCKET": "b",
           "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s", "BACKUP_PUBLIC_KEY": public}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("BACKUP_KEEP_DAYS", raising=False)
    assert backup._config()["keep_days"] == 30
    monkeypatch.setenv("BACKUP_KEEP_DAYS", "abc")
    assert backup._config()["keep_days"] == 30
    monkeypatch.setenv("R2_ENDPOINT", "http://insecure")
    assert backup._config() is None
    monkeypatch.setenv("R2_ENDPOINT", env["R2_ENDPOINT"])
    monkeypatch.setenv("BACKUP_PUBLIC_KEY", "broken")
    assert backup._config() is None
    monkeypatch.delenv("R2_BUCKET")
    assert backup._config() is None


def test_backup_loop_disabled_without_config(monkeypatch):
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    asyncio.run(asyncio.wait_for(backup.backup_loop(), timeout=2))


def test_backup_tool_keygen_and_decrypt(tmp_path, capsys):
    from scripts import backup_tool

    key_file = tmp_path / "private.key"
    backup_tool.main(["keygen", str(key_file)])
    public = capsys.readouterr().out.split("BACKUP_PUBLIC_KEY=")[1].strip()
    assert (key_file.stat().st_mode & 0o777) == 0o600
    blob = tmp_path / "b.enc"
    blob.write_bytes(encrypt(gzip.compress(b'{"ok": 1}'), public))
    out = tmp_path / "out.json"
    backup_tool.main(["decrypt", str(blob), str(key_file), str(out)])
    assert json.loads(out.read_text()) == {"ok": 1}
    assert (out.stat().st_mode & 0o777) == 0o600
    with pytest.raises(SystemExit):
        backup_tool.main(["decrypt", str(blob), str(key_file), str(out)])  # не перезаписывает
    with pytest.raises(SystemExit):
        backup_tool.main(["keygen", str(key_file)])  # не перезаписывает ключ


def test_dump_auth_users_pages_until_empty(monkeypatch):
    monkeypatch.setattr(backup, "_PAGE", 2)
    User = type("U", (), {})

    def user(i):
        u = User()
        u.id, u.email, u.phone, u.created_at, u.app_metadata = i, f"{i}@x", None, "", {"providers": ["email"]}
        return u

    pages = [[user(1), user(2)], [user(3)], []]
    calls = []

    async def fake_run_query(func, *a, **kw):
        calls.append(kw["page"])
        return pages.pop(0)

    monkeypatch.setattr(backup, "run_query", fake_run_query)
    users = asyncio.run(backup._dump_auth_users())
    assert [u["id"] for u in users] == ["1", "2", "3"]
    assert calls == [1, 2, 3]

    # API, игнорирующий page, не зацикливает выгрузку
    async def same_page(func, *a, **kw):
        return [user(1)]

    monkeypatch.setattr(backup, "run_query", same_page)
    with pytest.raises(RuntimeError):
        asyncio.run(backup._dump_auth_users())


def test_last_backup_time_ignores_future_names():
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H-%M-%SZ"
    past = f"backups/{(now - timedelta(hours=30)).strftime(fmt)}.json.gz.enc"
    future = f"backups/{(now + timedelta(days=365)).strftime(fmt)}.json.gz.enc"
    last = asyncio.run(backup._last_backup_time(FakeR2([past, future])))
    assert last == backup._key_time(past)
