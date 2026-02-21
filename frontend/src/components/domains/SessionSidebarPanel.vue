<template>
          <section v-if="leftNavSection === 'session'" class="card">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">forum</span>会话</h3>
              <div class="subtle mono">{{ sessionId ?? "—" }}</div>
            </div>
            <div v-if="lastStructuredTrace.length" class="traceStructured">
              <div v-for="step in lastStructuredTrace" :key="step.key" class="traceStep" :class="`is-${step.level}`">
                <div class="traceStepHead">
                  <span class="traceStepPhase">{{ step.phase }}</span>
                  <span class="traceStepTitle">{{ step.title }}</span>
                </div>
                <div v-if="step.detail" class="traceStepDetail">{{ step.detail }}</div>
              </div>
            </div>
            <details v-if="lastEvents.length" class="events">
              <summary>原始事件</summary>
              <pre class="code">{{ JSON.stringify(lastEvents, null, 2) }}</pre>
            </details>
            <div v-else class="subtle">暂无工具调用。</div>
          </section>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue"

export default defineComponent({
  name: "SessionSidebarPanel",
  props: {
    ctx: {
      type: Object as PropType<Record<string, any>>,
      required: true,
    },
  },
  setup(props) {
    return props.ctx
  },
})
</script>
