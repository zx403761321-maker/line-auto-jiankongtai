// 设备异常判定（读侧派生，与 risk_status/account_status 一致）。
// 返回设备当前命中的异常 dimension；无异常返回 null。
// 优先级（每台设备最多命中一个）：account_needs_replacement > risk_critical > device_offline
export function deviceAnomalyOf(d) {
  if (d.account_status === 'needs_replacement') return 'account_needs_replacement'
  if (d.risk_status === 'critical') return 'risk_critical'
  if (d.online_status === 'offline') return 'device_offline'
  return null
}
