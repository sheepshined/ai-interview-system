<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import Rail from './components/Rail.vue'
import Icon from './components/Icon.vue'
import { toastState } from './composables/useToast'

const route = useRoute()
const layout = computed(() => route.meta.layout || 'app')

// 统筹智能体抽屉异步挂载: 把 katex/markdown 依赖移出首屏 chunk,
// 首帧渲染完成后再按需拉取 (idle 时), 不影响首屏体积与绘制
const AssistantDock = defineAsyncComponent(() => import('./components/assistant/AssistantDock.vue'))
const dockMounted = ref(false)
onMounted(() => {
  const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 300))
  idle(() => { dockMounted.value = true })
})

function closeRail() {
  document.body.classList.remove('rail-open')
}
</script>

<template>
  <div v-if="layout === 'app'" class="shell">
    <Rail />
    <div class="rail-scrim" @click="closeRail"></div>
    <div class="main">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </div>
  </div>

  <RouterView v-else v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>

  <!-- 全局吐司 -->
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toastState.list" :key="t.id" class="toast is-on">
        <span class="tag-ic">
          <Icon :name="t.type === 'ok' ? 'checkCircle' : (t.type === 'warn' ? 'alert' : t.type)" />
        </span>
        <span>{{ t.text }}</span>
      </div>
    </TransitionGroup>
  </div>

  <!-- v2.0 统筹智能体: 挂在根上, bare 布局页(首页/面试间)同样可用;
       position:fixed, 不进文档流, 不影响 .main 的滚动; 异步首帧后挂载 -->
  <AssistantDock v-if="dockMounted" />
</template>