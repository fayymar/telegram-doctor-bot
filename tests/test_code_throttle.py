from bot import shared


def test_code_attempts_blocked_after_limit():
    uid = 424242
    shared._code_failures.pop(uid, None)
    for _ in range(shared._CODE_FAIL_LIMIT):
        assert not shared.code_attempts_blocked(uid)
        shared.record_failed_code_attempt(uid)
    assert shared.code_attempts_blocked(uid)
    assert not shared.code_attempts_blocked(uid + 1)
