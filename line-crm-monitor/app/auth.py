"""登录/登出 + 防暴力（固定延迟 + 按用户名失败锁定；内存级，单 worker 生效）。"""
import asyncio
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request

from . import users

router = APIRouter(prefix="/auth", tags=["auth"])

# 防暴力参数（公网第一道闸；叠加在 pbkdf2 600000 迭代之上，进一步压低爆破速率）
_FAIL_WINDOW = 300     # 失败计数窗口（秒）；锁定 = 窗口内失败满 _MAX_FAILS，持续到记录滑出窗口
_MAX_FAILS = 5         # 窗口内最大失败次数
_BASE_DELAY = 0.5      # 每次失败的基础延迟（秒）

_failures: dict[str, list[float]] = defaultdict(list)


def _prune(username: str) -> list[float]:
    """清掉窗口外的失败记录，返回当前窗口内失败时间戳列表。"""
    now = time.time()
    kept = [t for t in _failures.get(username, []) if now - t < _FAIL_WINDOW]
    if kept:
        _failures[username] = kept
    else:
        _failures.pop(username, None)
    return kept


def _locked(username: str) -> bool:
    return len(_prune(username)) >= _MAX_FAILS


def _record_failure(username: str) -> None:
    _failures[username].append(time.time())


@router.post("/login")
async def login(request: Request, body: dict):
    username = body.get("username", "") if isinstance(body, dict) else ""
    password = body.get("password", "") if isinstance(body, dict) else ""

    # 已锁定：直接拒绝（detail 与错误密码一致，不暴露锁定态）
    if username and _locked(username):
        await asyncio.sleep(_BASE_DELAY)
        raise HTTPException(status_code=401, detail="invalid username or password")

    user = await users.get_user(username)
    ok = (
        user is not None
        and user["is_active"]
        and users.verify_password(password, user["password_hash"])
    )
    if not ok:
        if username:
            _record_failure(username)
        await asyncio.sleep(_BASE_DELAY)
        raise HTTPException(status_code=401, detail="invalid username or password")

    _failures.pop(username, None)   # 成功清除失败计数
    request.session["user"] = {
        "username": user["username"],
        "role": user["role"],
        "group_id": user["group_id"],
    }
    return {"ok": True, "username": user["username"], "role": user["role"]}


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}
