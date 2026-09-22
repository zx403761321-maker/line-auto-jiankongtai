"""risk_status 读侧派生（纯函数，无 DB/网络/配置依赖，便于单测与未来多信号扩展）。"""


def derive_risk_status(risk_score, needs_replacement, warn_threshold, crit_threshold):
    """根据业务风险信号派生三态 risk_status。

    优先级（高到低）：
      1. needs_replacement（业务已判定「需换号」）→ critical
      2. risk_score >= crit_threshold                      → critical
      3. risk_score >= warn_threshold                      → warning
      4. 其余                                             → normal

    返回 (risk_status, risk_reason)：
      risk_status: 'normal' | 'warning' | 'critical'
      risk_reason : 'needs_replacement' | 'risk_score' | None

    预留扩展：未来多信号（如 task_result 失败率、冷却频次）触发时，
    在此函数内按优先级追加分支即可，无需改调用方。
    """
    if needs_replacement:
        return ("critical", "needs_replacement")
    if risk_score >= crit_threshold:
        return ("critical", "risk_score")
    if risk_score >= warn_threshold:
        return ("warning", "risk_score")
    return ("normal", None)
