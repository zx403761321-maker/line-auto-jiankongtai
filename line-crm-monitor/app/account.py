"""account_status 读侧派生（纯函数，无 DB/网络/配置依赖，便于单测）。"""
from datetime import datetime, timezone


def derive_account_status(needs_replacement, cooldown_until, now=None):
    """根据账号生命周期信号派生三态 account_status（账号生命周期展示状态）。

    数据源 = device_limit_status.json（业务机 template.sh 写，不受 /health 污染），
    经 monitor-agent heartbeat 快照映射为 devices.needs_replacement / cooldown_until。
    注意：**不是** bridge.db.account_status.status（那个被 /health 每 30s 冲成
    online/offline，不可信）。

    优先级（高到低）：
      1. needs_replacement（业务已判定「需换号」，累计 3 次触顶）→ needs_replacement
      2. cooldown_until 在未来（冷却期内）                        → cooling_down
      3. 其余                                                     → active

    cooldown_until 精度说明：
      业务侧 device_limit_status.json 只存日期 YYYY-MM-DD；monitor-agent 将其解析为
      对应日期 00:00 Asia/Taipei 并转 UTC 存入中央。因此到截止日 00:00 即满足
      cooldown_until <= now，恢复 active —— 与业务侧 template.sh check_cooldown
      的「now < until 才冷却」逻辑一致（此处用严格大于 > now 判冷却）。

    cooldown_count 不参与当前状态判断（历史累计次数），仅保留展示/统计用途。

    返回 (account_status, account_reason)：
      account_status: 'active' | 'cooling_down' | 'needs_replacement'
      account_reason : 'needs_replacement' | 'cooldown' | None
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if needs_replacement:
        return ("needs_replacement", "needs_replacement")
    if cooldown_until is not None and cooldown_until > now:
        return ("cooling_down", "cooldown")
    return ("active", None)
