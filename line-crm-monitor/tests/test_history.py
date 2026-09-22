"""detect_anomaly_history 翻转检测单测（纯函数，无 DB/网络依赖）。

运行方式（二选一）：
  python3 tests/test_history.py        # 零依赖，直接跑
  pytest tests/test_history.py         # 若已装 pytest
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.history import detect_anomaly_history

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def _t(minute):
    return NOW.replace(minute=minute)


def test_empty_no_anomaly():
    r = detect_anomaly_history([], lambda v: v, False)
    assert r == {"first_at": None, "last_at": None, "count": 0, "recovered": False}


def test_never_anomalous():
    obs = [(_t(1), False), (_t(2), False), (_t(3), False)]
    r = detect_anomaly_history(obs, lambda v: v, False)
    assert r["first_at"] is None
    assert r["last_at"] is None
    assert r["count"] == 0
    assert r["recovered"] is False


def test_single_occurrence():
    obs = [(_t(1), False), (_t(2), True), (_t(3), True)]
    r = detect_anomaly_history(obs, lambda v: v, True)
    assert r["first_at"] == _t(2)
    assert r["last_at"] == _t(2)
    assert r["count"] == 1
    assert r["recovered"] is False


def test_multiple_flips():
    obs = [(_t(1), False), (_t(2), True), (_t(3), False), (_t(4), True)]
    r = detect_anomaly_history(obs, lambda v: v, True)
    assert r["first_at"] == _t(2)
    assert r["last_at"] == _t(4)
    assert r["count"] == 2
    assert r["recovered"] is False


def test_starts_anomalous():
    # 窗口起点已异常：first_at = 窗口内第一次观测时间，count 从 1 起
    obs = [(_t(1), True), (_t(2), True)]
    r = detect_anomaly_history(obs, lambda v: v, True)
    assert r["first_at"] == _t(1)
    assert r["last_at"] == _t(1)
    assert r["count"] == 1


def test_recovered():
    # 曾异常 → 当前已恢复
    obs = [(_t(1), False), (_t(2), True), (_t(3), False)]
    r = detect_anomaly_history(obs, lambda v: v, False)
    assert r["count"] == 1
    assert r["first_at"] == _t(2)
    assert r["last_at"] == _t(2)
    assert r["recovered"] is True


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
