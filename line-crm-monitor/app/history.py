"""异常历史翻转检测（纯函数，零依赖，便于单测）。"""


def detect_anomaly_history(observations, is_anomalous, current_anomalous):
    """从按时间升序的观测序列检测异常历史。

    observations: list[tuple[datetime, value]]（时间升序）
    is_anomalous: callable(value) -> bool，判断单个观测值是否异常
    current_anomalous: bool，当前快照该维度是否异常（用于 recovered）

    返回 dict:
      first_at: 查询时间窗口内首次观测到异常的时间（datetime 或 None）。
                NOTE: 仅代表「窗口内首次观测」，不代表设备生命周期首次异常。
      last_at:  最后一次「正常→异常」翻转的时间（datetime 或 None）。
      count:    「正常→异常」翻转次数（int）。
      recovered: 曾发生异常(count>0)且当前已恢复正常。
    """
    first_at = None
    last_at = None
    count = 0
    prev = False  # 上一次观测是否异常
    for ts, value in observations:
        anomalous = bool(is_anomalous(value))
        if anomalous:
            if first_at is None:
                first_at = ts
            if not prev:
                count += 1
                last_at = ts
        prev = anomalous
    return {
        "first_at": first_at,
        "last_at": last_at,
        "count": count,
        "recovered": count > 0 and not current_anomalous,
    }
