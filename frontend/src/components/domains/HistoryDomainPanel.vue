<template>
          <section v-if="leftNavSection === 'history'" class="card">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">history</span>历史</h3>
              <button
                class="ghostBtn"
                :disabled="historyTab === 'sessions' ? historySessionsBusy : historyTab === 'files' ? historyFilesBusy : historySearchBusy"
                type="button"
                @click="
                  historyTab === 'sessions'
                    ? refreshHistorySessions()
                    : historyTab === 'files'
                      ? refreshHistoryFiles()
                      : runHistoryDirectorySearch()
                "
              >
                刷新
              </button>
            </div>

            <div class="tabs skillsTabs">
              <button class="tab" :class="{ active: historyTab === 'sessions' }" type="button" @click="historyTab = 'sessions'">
                会话
              </button>
              <button class="tab" :class="{ active: historyTab === 'files' }" type="button" @click="historyTab = 'files'">文件</button>
              <button class="tab" :class="{ active: historyTab === 'search' }" type="button" @click="historyTab = 'search'">目录检索</button>
            </div>

            <label class="select wide historyScope">
              <span class="label">范围</span>
              <select v-model="historyScope">
                <option value="current">当前项目</option>
                <option value="all">全部项目</option>
              </select>
            </label>

            <div v-if="historyTab === 'search'" class="historySearchPanel">
              <div class="subtle">
                命令示例：<code>grep 报检单 --workspace --path=docs</code>、<code>grep session --history</code>、<code>grep 交付 --all</code>
              </div>
              <div class="row compactRow wrapRow">
                <input
                  v-model="historyDirectoryCommand"
                  class="input"
                  placeholder="输入命令检索目录内容（如：grep 报检单 --workspace --path=docs）"
                  @keydown.enter.prevent="runHistoryDirectorySearch()"
                />
                <button class="primaryBtn" :disabled="historySearchBusy || !historyDirectoryCommand.trim()" type="button" @click="runHistoryDirectorySearch()">
                  检索
                </button>
                <button v-if="historyDirectoryCommand.trim()" class="ghostBtn" type="button" @click="historyDirectoryCommand = ''">清空</button>
              </div>
              <div class="historyHintRow">
                <button
                  class="ghostBtn chipBtn"
                  type="button"
                  @click="historyDirectoryCommand = 'grep 报检单 --workspace --path=docs'; runHistoryDirectorySearch()"
                >
                  搜 docs/报检单
                </button>
                <button class="ghostBtn chipBtn" type="button" @click="historyDirectoryCommand = 'grep session --history'; runHistoryDirectorySearch()">
                  搜历史快照
                </button>
                <button class="ghostBtn chipBtn" type="button" @click="historyDirectoryCommand = 'grep 交付 --all'; runHistoryDirectorySearch()">
                  跨项目检索
                </button>
              </div>

              <div v-if="historySearchBusy" class="historySkeleton"><div v-for="n in 4" :key="n" class="skeletonLine" /></div>
              <div v-else-if="!historySearchExecuted" class="subtle">输入命令后执行目录检索。</div>
              <div v-else-if="historySearchHits.length === 0" class="subtle">没有匹配结果。</div>
              <div v-else class="historyList">
                <div
                  v-for="hit in historySearchHits"
                  :key="`${hit.source}:${hit.absolute_path}:${hit.line_no}:${hit.column_no}`"
                  class="historyItem historySearchItem"
                >
                  <div class="historyItemMain">
                    <div class="historyTitle">{{ hit.rel_path }}</div>
                    <div class="historyMetaRow">
                      <span class="metaPill">{{ hit.source === "workspace" ? "项目目录" : "历史快照" }}</span>
                      <span class="mono">Ln {{ hit.line_no }} · Col {{ hit.column_no }}</span>
                    </div>
                    <div class="historySnippet">{{ hit.preview }}</div>
                    <div class="subtle mono">{{ hit.absolute_path }}</div>
                  </div>
                  <div class="historyActions">
                    <button class="ghostBtn" type="button" @click="copyToClipboard(hit.absolute_path)">复制路径</button>
                    <button class="ghostBtn" type="button" @click="copyToClipboard(`${hit.absolute_path}:${hit.line_no}`)">复制定位</button>
                  </div>
                </div>
              </div>
            </div>

            <template v-else>
              <div class="row">
                <input v-model="historySearch" class="input" placeholder="搜索会话/文件…" />
                <button v-if="historySearch.trim()" class="ghostBtn" type="button" @click="historySearch = ''">清空</button>
              </div>

              <div v-if="historyTab === 'sessions'">
                <div v-if="historySessionsBusy" class="historySkeleton"><div v-for="n in 4" :key="n" class="skeletonLine" /></div>
                <div v-else-if="historySessions.length === 0" class="subtle">暂无历史会话。</div>
                <div v-else-if="filteredHistorySessions.length === 0" class="subtle">没有匹配的会话。</div>
                <div v-else class="historyList">
                  <div
                    v-for="s in filteredHistorySessions"
                    :key="s.session_id"
                    class="historyItem"
                    :class="{ active: selectedHistorySessionId === s.session_id }"
                  >
                    <button class="historyItemMain" type="button" @click="openHistorySession(s.session_id)">
                      <div class="historyTitle">{{ s.title || (s.last_message ?? "") || s.session_id }}</div>
                      <div v-if="historyScope === 'all'" class="historyMetaRow">
                        <span class="metaPill">{{ projectNameFromId(s.project_id) }}</span>
                      </div>
                      <div v-if="s.last_message" class="historySnippet">{{ s.last_message }}</div>
                      <div class="historyMetaRow">
                        <span>{{ formatIsoTime(s.updated_at) }}</span>
                        <span class="mono">{{ s.provider }}{{ s.model ? ` · ${s.model}` : "" }}</span>
                      </div>
                    </button>
                    <div class="historyActions">
                      <button class="ghostBtn" type="button" @click="openHistorySession(s.session_id)">打开</button>
                      <button class="ghostBtn" type="button" @click="removeHistorySession(s.session_id)">删除</button>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else>
                <label class="select wide historyScope">
                  <span class="label">类型</span>
                  <select v-model="historyFileKindFilter">
                    <option value="">全部</option>
                    <option value="generated">生成</option>
                    <option value="file">文件</option>
                    <option value="image">图片</option>
                  </select>
                </label>
                <div v-if="historyFilesBusy" class="historySkeleton"><div v-for="n in 4" :key="n" class="skeletonLine" /></div>
                <div v-else-if="historyFiles.length === 0" class="subtle">暂无历史文件。</div>
                <div v-else-if="filteredHistoryFiles.length === 0" class="subtle">没有匹配的文件。</div>
                <div v-else class="historyList">
                  <div v-for="f in filteredHistoryFiles" :key="f.file_id" class="fileItem fileItemCompact">
                    <div class="fileIcon" :data-kind="_fileKindFromId(f.filename || f.file_id)">
                      {{ _fileKindFromId(f.filename || f.file_id).toUpperCase() }}
                    </div>
                    <div class="fileMeta">
                      <div class="fileName">{{ f.filename || f.file_id }}</div>
                      <div class="subtle">
                        {{ formatBytes(f.size_bytes) }} · {{ f.kind }} · {{ formatIsoTime(f.created_at) }}
                        <template v-if="historyScope === 'all'"> · {{ projectNameFromId(f.project_id) }}</template>
                      </div>
                      <div v-if="f.session_id" class="subtle mono">会话：{{ f.session_id }}</div>
                    </div>
                    <div class="fileActions">
                      <a class="primaryBtn" :href="toAbsoluteUrl(f.download_url)" target="_blank" rel="noreferrer">下载</a>
                      <button class="ghostBtn" type="button" @click="copyToClipboard(toAbsoluteUrl(f.download_url))">复制</button>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <div v-if="historyError" class="error">{{ historyError }}</div>
          </section>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue"

export default defineComponent({
  name: "HistoryDomainPanel",
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
