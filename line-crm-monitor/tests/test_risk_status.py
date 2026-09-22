"""risk_status 派生规则单测（纯函数，无 DB/网络依赖）。

运行方式（二选一）：
  python tests/test_risk_status.py        # 零依赖，直接跑
  pytest tests/test_risk_status.py        # 若已装 pytest
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.risk import derive_risk_status

WARN, CRIT = 40, 90


def _derive(risk_score, needs_replacement=False):
    return derive_risk_status(risk_score, needs_replacement, WARN, CRIT)


def test_needs_replacement_priority():
    # 业务判定「需换号」优先级最高；即使分数已达 critical 线，reason 仍是 needs_replacement
    assert _derive(100, True) == ("critical", "needs_replacement")


def test_critical_by_score_above():
    # needs_replacement=false 但分数超 critical 阈值 → critical
    assert _derive(100, False) == ("critical", "risk_score")


def test_critical_boundary():
    # 锁定 >= 判断：risk_score == 90（临界值）即 critical
    assert _derive(90, False) == ("critical", "risk_score")


def test_warning_above():
    assert _derive(50, False) == ("warning", "risk_score")


def test_warning_boundary():
    # 锁定 >= 判断：risk_score == 40（临界值）即 warning
    assert _derive(40, False) == ("warning", "risk_score")


def test_normal():
    assert _derive(0, False) == ("normal", None)


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
