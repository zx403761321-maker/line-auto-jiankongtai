"""account_status 派生规则单测（纯函数，无 DB/网络依赖）。

运行方式（二选一）：
  python3 tests/test_account_status.py        # 零依赖，直接跑
  pytest tests/test_account_status.py         # 若已装 pytest
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.account import derive_account_status

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=3)
PAST = NOW - timedelta(days=1)


def _derive(needs_replacement=False, cooldown_until=None):
    return derive_account_status(needs_replacement, cooldown_until, now=NOW)


def test_needs_replacement_priority():
    # 换号优先级最高：即使 cooldown_until 仍在未来，也判 needs_replacement
    assert _derive(True, FUTURE) == ("needs_replacement", "needs_replacement")


def test_needs_replacement_without_cooldown():
    # 换号独立于冷却：cooldown_until 为空也判 needs_replacement
    assert _derive(True, None) == ("needs_replacement", "needs_replacement")


def test_cooling_down_future():
    # 非换号 + 冷却期内（cooldown_until 在未来）→ cooling_down
    assert _derive(False, FUTURE) == ("cooling_down", "cooldown")


def test_cooldown_expired_past():
    # 冷却已到期（cooldown_until 在过去）→ active
    assert _derive(False, PAST) == ("active", None)


def test_no_cooldown_null():
    assert _derive(False, None) == ("active", None)


def test_cooldown_boundary_equal():
    # 锁定严格大于：cooldown_until == now（截止日 00:00 已到）→ active
    assert _derive(False, NOW) == ("active", None)


if __name__ == "__main__":
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
