/* 数字滚动: easeOutCubic, 供总览卡/统计卡的 count-up 微交互。
   opts.from: 起始值 (刷新续滚用, 默认 0); opts.dur: 时长毫秒 */
export function animateValue(target, setter, opts = {}) {
  const dur = opts.dur ?? 1100
  const from = Number(opts.from) || 0
  const start = performance.now()
  const tick = (now) => {
    const t = Math.min(1, (now - start) / dur)
    const eased = 1 - Math.pow(1 - t, 3)
    setter(from + (target - from) * eased)
    if (t < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}
