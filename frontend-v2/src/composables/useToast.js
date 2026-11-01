import { reactive } from 'vue'

/* 全局吐司：App.vue 渲染 <ToastHost/>，任意位置调用 toast('已保存') */
export const toastState = reactive({ list: [] })
let seq = 0

export function toast(text, type = 'ok', ms = 2600) {
  const id = ++seq
  toastState.list.push({ id, text, type })
  setTimeout(() => {
    const i = toastState.list.findIndex((t) => t.id === id)
    if (i >= 0) toastState.list.splice(i, 1)
  }, ms)
}