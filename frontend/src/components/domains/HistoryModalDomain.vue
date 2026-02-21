<template>
      <div v-if="showHistoryModal" class="modalOverlay" @click.self="closeHistoryModal">
        <div class="modal historyModal">
          <div class="modalHead">
            <div>
              <div class="modalTitle">历史会话</div>
              <div v-if="historyDetail?.session" class="subtle">
                项目：{{ projectNameFromId(historyDetail.session.project_id) }} · 更新时间：{{ formatIsoTime(historyDetail.session.updated_at) }}
              </div>
              <div class="subtle mono">{{ historyDetail?.session?.session_id ?? selectedHistorySessionId ?? "" }}</div>
	            </div>
	            <div class="row">
	              <button
	                v-if="historyDetail?.session?.session_id"
	                class="primaryBtn"
	                type="button"
	                @click="loadHistoryIntoChat"
	              >
	                加载到对话
	              </button>
	              <button
	                v-if="historyDetail?.session?.session_id"
	                class="ghostBtn"
	                type="button"
                @click="copyToClipboard(historyDetail.session.session_id)"
              >
                复制ID
              </button>
              <button
                v-if="historyDetail?.session?.session_id"
                class="ghostBtn"
                type="button"
                @click="removeHistorySession(historyDetail.session.session_id)"
              >
                删除
              </button>
              <button class="ghostBtn" type="button" @click="closeHistoryModal">关闭</button>
            </div>
          </div>

          <div v-if="historyDetailBusy" class="subtle">正在加载…</div>
          <div v-else-if="historyDetailError" class="error">{{ historyDetailError }}</div>

          <div v-else-if="historyDetail" class="historyModalBody">
            <div v-for="m in historyDetail.messages" :key="m.id" class="bubble" :class="m.role">
              <div class="bubbleMeta">
                <span class="who">{{ m.role === 'user' ? '你' : 'AI' }}</span>
                <span class="when">{{ formatIsoTime(m.created_at) }}</span>
              </div>
              <template v-if="m.role === 'assistant'">
                <div class="md" v-html="renderMarkdown(historyMessageContent(m))" />
                <div v-if="m.attachments?.some((a: any) => a.kind === 'image')" class="attachmentGrid">
                  <a
                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'image')"
                    :key="`${idx}-${a.download_url}`"
                    class="attachmentLink"
                    :href="a.download_url"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img :src="a.download_url" :alt="a.filename ?? 'image'" loading="lazy" />
                  </a>
                </div>
                <div v-if="m.attachments?.some((a: any) => a.kind === 'file')" class="fileChips">
                  <a
                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'file')"
                    :key="`${idx}-${a.download_url}`"
                    class="fileChip"
                    :href="a.download_url"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span class="fileChipIcon" :data-kind="_fileKindFromId(a.filename ?? a.file_id ?? '')">
                      {{ _fileKindFromId(a.filename ?? a.file_id ?? "").toUpperCase() }}
                    </span>
                    <span class="fileChipName">{{ a.filename ?? a.file_id ?? "file" }}</span>
                  </a>
                </div>
	                <div v-if="historyMessageDownloads(m).length" class="downloadList">
	                  <div v-for="d in historyMessageDownloads(m)" :key="d.absolute" class="downloadBlock">
	                    <div class="downloadRow">
	                      <a class="primaryBtn" :href="d.absolute" target="_blank" rel="noreferrer">下载文件</a>
	                      <button class="ghostBtn" type="button" @click="copyToClipboard(d.absolute)">复制链接</button>
	                    </div>
	                    <div class="subtle mono downloadUrl">{{ d.absolute }}</div>
	                  </div>
	                </div>
	                <details v-if="showTrace && historyEventsOf(m).length" class="trace">
                  <summary>执行轨迹（不含模型内部思维）</summary>
                  <div class="traceStructured">
                    <div
                      v-for="step in structuredTrace(historyEventsOf(m))"
                      :key="step.key"
                      class="traceStep"
                      :class="`is-${step.level}`"
                    >
                      <div class="traceStepHead">
                        <span class="traceStepPhase">{{ step.phase }}</span>
                        <span class="traceStepTitle">{{ step.title }}</span>
                      </div>
                      <div v-if="step.detail" class="traceStepDetail">{{ step.detail }}</div>
                    </div>
                  </div>
                  <ol class="traceList">
                    <li v-for="(s, idx) in summarizeTrace(historyEventsOf(m))" :key="idx">{{ s }}</li>
                  </ol>
                  <details class="traceRaw">
                    <summary>原始事件</summary>
                    <pre class="code">{{ JSON.stringify(historyEventsOf(m), null, 2) }}</pre>
                  </details>
                </details>
	              </template>
              <div v-else class="plain">
                {{ historyMessageContent(m) }}
                <div v-if="m.attachments?.some((a: any) => a.kind === 'image')" class="attachmentGrid">
                  <a
                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'image')"
                    :key="`${idx}-${a.download_url}`"
                    class="attachmentLink"
                    :href="a.download_url"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img :src="a.download_url" :alt="a.filename ?? 'image'" loading="lazy" />
                  </a>
                </div>
                <div v-if="m.attachments?.some((a: any) => a.kind === 'file')" class="fileChips">
                  <a
                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'file')"
                    :key="`${idx}-${a.download_url}`"
                    class="fileChip"
                    :href="a.download_url"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span class="fileChipIcon" :data-kind="_fileKindFromId(a.filename ?? a.file_id ?? '')">
                      {{ _fileKindFromId(a.filename ?? a.file_id ?? "").toUpperCase() }}
                    </span>
                    <span class="fileChipName">{{ a.filename ?? a.file_id ?? "file" }}</span>
                  </a>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="subtle">未选择会话。</div>
        </div>
      </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue"

export default defineComponent({
  name: "HistoryModalDomain",
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
