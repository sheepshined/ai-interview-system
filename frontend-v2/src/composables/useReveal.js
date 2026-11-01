/* 滚动进入视口后揭示：v-reveal / v-reveal="0.12"（延迟秒） */
export const reveal = {
  mounted(el, binding) {
    el.classList.add('rv')
    if (binding.value) el.style.setProperty('--d', `${binding.value}s`)
    // 父级 [data-stagger] 内的子元素自动错峰
    const parent = el.parentElement?.closest('[data-stagger]')
    if (parent && !el.style.getPropertyValue('--d')) {
      const idx = Array.from(parent.children).indexOf(el)
      el.style.setProperty('--d', `${(Math.max(idx, 0) * 0.07).toFixed(2)}s`)
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          en.target.classList.add('is-in')
          io.unobserve(en.target)
        }
      })
    }, { threshold: 0.16, rootMargin: '0px 0px -6% 0px' })
    io.observe(el)
    el._rvObserver = io
  },
  unmounted(el) {
    el._rvObserver?.disconnect()
  },
}