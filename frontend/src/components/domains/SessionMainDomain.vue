<template>
        <main
          class="main"
          @dragenter="onChatDragEnter"
          @dragover="onChatDragOver"
          @dragleave="onChatDragLeave"
          @drop="onChatDrop"
        >
          <div v-if="draggingFiles" class="dropOverlay" aria-hidden="true">
            <div class="dropOverlayInner">拖拽文件到此处上传</div>
          </div>
          <div class="chatHead">
            <div>
              <h2 class="chatTitle"><span class="msIcon h2Icon" aria-hidden="true">chat</span>对话</h2>
              <div class="chatMeta">
                <span class="metaPill">工作区：{{ activeWorkspaceLabel }}</span>
                <span class="metaPill">档案：{{ activeAgentProfile.name }}</span>
                <span class="metaPill">安全：{{ securityPresetLabel }}</span>
                <span class="metaPill">Enter 发送</span>
                <span class="metaPill">Shift+Enter 换行</span>
              </div>
            </div>
            <div class="chatActions">
              <button class="ghostBtn iconBtn" :class="{ active: showLeft }" type="button" @click="showLeft = !showLeft">
                <span class="msIcon btnIcon" aria-hidden="true">left_panel_open</span>
                <span>左栏</span>
              </button>
              <button class="ghostBtn iconBtn" :class="{ active: showRight }" type="button" @click="showRight = !showRight">
                <span class="msIcon btnIcon" aria-hidden="true">right_panel_open</span>
                <span>预览</span>
              </button>
              <button class="ghostBtn iconBtn" type="button" @click="showTrace = !showTrace">
                <span class="msIcon btnIcon" aria-hidden="true">visibility</span>
                <span>{{ showTrace ? "隐藏轨迹" : "显示轨迹" }}</span>
              </button>
              <button class="ghostBtn iconBtn" :disabled="sending" type="button" @click="reset">
                <span class="msIcon btnIcon" aria-hidden="true">add_comment</span>
                <span>新会话</span>
              </button>
            </div>
          </div>

          <div ref="chatBodyRef" class="chatBody" @scroll="onChatBodyScroll">
            <div v-if="messages.length === 0" class="empty">
              <div class="emptyTitle">从一个任务开始</div>
              <div class="emptyHint">例如：写报价单、写方案 PPT、做原型、或者帮我改代码。</div>
              <div class="emptyChips">
                <button class="suggestChip" type="button" @click="applyQuickPrompt('帮我做一份《大模型培训（全员版）》8页PPT：时长=60分钟，方向=通识+办公提效+安全合规。')">
                  生成培训 PPT
                </button>
                <button class="suggestChip" type="button" @click="applyQuickPrompt('根据以下产品清单生成一份报价单（含 Excel 下载）：\\n1) 产品A，数量=1，单价=\\n2) 产品B，数量=，单价=')">
                  生成报价单
                </button>
                <button class="suggestChip" type="button" @click="applyQuickPrompt('帮我做一个多页面原型（HTML打包ZIP）：\\n- 页面：登录、列表、详情、设置\\n- 风格：现代简洁\\n- 输出：可点击跳转')">
                  生成原型 ZIP
                </button>
                <button class="suggestChip" type="button" @click="applyQuickPrompt('帮我优化这个项目的前端界面：统一视觉风格、提升可用性、移动端适配。')">
                  优化界面
                </button>
              </div>
            </div>

	            <div v-for="m in messages" :key="m.id" class="bubble" :class="m.role">
              <div class="bubbleMeta">
                <span class="who">{{ m.role === 'user' ? '你' : 'AI' }}</span>
                <span class="when">{{ formatTime(m.ts) }}</span>
              </div>
	              <template v-if="m.role === 'assistant'">
                  <template v-if="assistantParts(m).summary">
                    <details class="thoughtBlock" open>
                      <summary>Thoughts</summary>
                      <div class="md" v-html="renderMarkdown(assistantParts(m).summary ?? '')" />
                    </details>
                    <div class="answerBlock">
                      <div class="answerLabel">Answer</div>
                      <div class="md" v-html="renderMarkdown(assistantParts(m).answer ?? '')" />
                    </div>
                  </template>
                  <div v-else class="md" v-html="renderMarkdown(m.content)" />
	                <div v-if="m.attachments?.some((a: any) => a.kind === 'image')" class="attachmentGrid">
	                  <a
	                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'image')"
	                    :key="`${idx}-${a.url}`"
	                    class="attachmentLink"
	                    :href="a.url"
	                    target="_blank"
	                    rel="noreferrer"
	                  >
	                    <img :src="a.url" :alt="a.filename ?? 'image'" loading="lazy" />
	                  </a>
	                </div>
	                <div v-if="m.attachments?.some((a: any) => a.kind === 'file')" class="fileChips">
	                  <a
	                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'file')"
	                    :key="`${idx}-${a.url}`"
	                    class="fileChip"
	                    :href="a.url"
	                    target="_blank"
	                    rel="noreferrer"
	                  >
	                    <span class="fileChipIcon" :data-kind="_fileKindFromId(a.filename ?? a.file_id ?? '')">
	                      {{ _fileKindFromId(a.filename ?? a.file_id ?? "").toUpperCase() }}
	                    </span>
	                    <span class="fileChipName">{{ a.filename ?? a.file_id ?? "file" }}</span>
	                  </a>
	                </div>
	                <div v-if="downloadsByMessageId[m.id]?.length" class="downloadList">
	                  <div v-for="d in downloadsByMessageId[m.id]" :key="d.absolute" class="downloadBlock">
	                    <div class="downloadRow">
                      <a class="primaryBtn" :href="d.absolute" target="_blank" rel="noreferrer">下载文件</a>
                      <button class="ghostBtn" type="button" @click="copyToClipboard(d.absolute)">复制链接</button>
                    </div>
                    <div class="subtle mono downloadUrl">{{ d.absolute }}</div>
                  </div>
                </div>
                <div v-if="quotePreviewByMessageId[m.id]" class="quotePreview">
                  <div class="quotePreviewHead">
                    <div class="quotePreviewTitle">
                      报价单预览（{{ (quotePreviewByMessageId[m.id]?.kind ?? "").toUpperCase() }}）
                    </div>
                    <div class="quoteMeta">
                      <span>供方：{{ quotePreviewByMessageId[m.id]?.seller }}</span>
                      <span>需方：{{ quotePreviewByMessageId[m.id]?.buyer }}</span>
                      <span>
                        合计：{{ formatMoney(quotePreviewByMessageId[m.id]?.total ?? 0) }}
                        {{ quotePreviewByMessageId[m.id]?.currency }}
                      </span>
                    </div>
                  </div>
                  <div class="quoteBody">
                    <table class="quoteTable">
                      <thead>
                        <tr>
                          <th>名称</th>
                          <th>数量</th>
                          <th>单位</th>
                          <th>单价</th>
                          <th>小计</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(it, idx) in quotePreviewByMessageId[m.id]?.items ?? []" :key="`${idx}-${it.name}`">
                          <td class="qName">{{ it.name }}</td>
                          <td class="qNum">{{ it.quantity }}</td>
                          <td class="qUnit">{{ it.unit ?? "项" }}</td>
                          <td class="qNum">{{ formatMoney(it.unit_price) }}</td>
                          <td class="qNum">{{ formatMoney(it.quantity * it.unit_price) }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <div v-if="quotePreviewByMessageId[m.id]?.note" class="quoteNote">
                      备注：{{ quotePreviewByMessageId[m.id]?.note }}
                    </div>
                  </div>
                </div>
                <div v-if="pptPreviewByMessageId[m.id]" class="pptPreview">
                  <div class="pptPreviewHead">
                    <div class="pptPreviewTitle">
                      PPT 预览（共
                      {{
                        pptPreviewByMessageId[m.id]?.slideImageUrls?.length
                          ? pptPreviewByMessageId[m.id].slideImageUrls.length
                          : (pptPreviewByMessageId[m.id]?.slides.length ?? 0) + 1
                      }}
                      页）
                    </div>
                    <div v-if="pptPreviewByMessageId[m.id]?.downloadUrl" class="protoActions">
                      <a class="ghostBtn" :href="pptPreviewByMessageId[m.id]?.downloadUrl" target="_blank" rel="noreferrer">下载</a>
                    </div>
                  </div>
                  <div class="pptSlides">
                    <template v-if="pptPreviewByMessageId[m.id]?.slideImageUrls?.length">
                      <div
                        v-for="(img, idx) in pptPreviewByMessageId[m.id]?.slideImageUrls ?? []"
                        :key="`${idx}-${img}`"
                        class="pptSlideCard pptCover pptCoverReal"
                      >
                        <div class="pptSlideNo">{{ idx + 1 }}</div>
                        <img class="pptCoverImage" :src="img" :alt="`PPT 第 ${idx + 1} 页`" loading="lazy" referrerpolicy="no-referrer" />
                        <div class="pptRealBadge">真实渲染</div>
                      </div>
                    </template>
                    <template v-else>
                      <div class="pptSlideCard pptCover" :class="{ pptCoverReal: !!pptPreviewByMessageId[m.id]?.coverImageUrl }">
                        <div class="pptSlideNo">1</div>
                        <img
                          v-if="pptPreviewByMessageId[m.id]?.coverImageUrl"
                          class="pptCoverImage"
                          :src="pptPreviewByMessageId[m.id]?.coverImageUrl"
                          alt="PPT 封面预览"
                          loading="lazy"
                          referrerpolicy="no-referrer"
                        />
                        <div v-else class="pptCoverTitle">{{ pptPreviewByMessageId[m.id]?.title ?? "" }}</div>
                        <div v-if="pptPreviewByMessageId[m.id]?.coverImageUrl" class="pptRealBadge">真实渲染</div>
                      </div>
                      <div
                        v-for="(s, idx) in pptPreviewByMessageId[m.id]?.slides ?? []"
                        :key="`${idx}-${s.title}`"
                        class="pptSlideCard"
                      >
                        <div class="pptSlideNo">{{ idx + 2 }}</div>
                        <div class="pptSlideTitle">{{ s.title }}</div>
                        <ul class="pptBullets">
                          <li v-for="(b, j) in s.bullets.slice(0, 5)" :key="j">{{ b }}</li>
                          <li v-if="s.bullets.length > 5" class="pptMore">…</li>
                        </ul>
                      </div>
                    </template>
                  </div>
                </div>
                <div v-if="protoPreviewByMessageId[m.id]" class="protoPreview">
                  <div class="protoPreviewHead">
                    <div class="protoPreviewTitle">原型预览：{{ protoPreviewByMessageId[m.id]?.project_name }}</div>
                    <div class="protoActions">
                      <a
                        class="ghostBtn"
                        :href="protoPreviewByMessageId[m.id]?.preview_url"
                        target="_blank"
                        rel="noreferrer"
                      >
                        新窗口打开
                      </a>
                      <button
                        class="ghostBtn"
                        type="button"
                        @click="copyToClipboard(protoPreviewByMessageId[m.id]?.preview_url ?? '')"
                      >
                        复制预览链接
                      </button>
                    </div>
                  </div>
                  <iframe
                    class="protoFrame"
                    :src="protoPreviewByMessageId[m.id]?.preview_url"
                    loading="lazy"
                    sandbox="allow-same-origin"
                    referrerpolicy="no-referrer"
                  />
                </div>
                <details v-if="showTrace && eventsByMessageId[m.id]?.length" class="trace">
                  <summary>执行轨迹（不含模型内部思维）</summary>
                  <div class="traceStructured">
                    <div
                      v-for="step in structuredTrace(eventsByMessageId[m.id] ?? [])"
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
                    <li v-for="(s, idx) in summarizeTrace(eventsByMessageId[m.id] ?? [])" :key="idx">{{ s }}</li>
                  </ol>
                  <details class="traceRaw">
                    <summary>原始事件</summary>
                    <pre class="code">{{ JSON.stringify(eventsByMessageId[m.id], null, 2) }}</pre>
                  </details>
                </details>
	              </template>
	              <div v-else class="plain">
	                {{ m.content }}
	                <div v-if="m.attachments?.some((a: any) => a.kind === 'image')" class="attachmentGrid">
	                  <a
	                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'image')"
	                    :key="`${idx}-${a.url}`"
	                    class="attachmentLink"
	                    :href="a.url"
	                    target="_blank"
	                    rel="noreferrer"
	                  >
	                    <img :src="a.url" :alt="a.filename ?? 'image'" loading="lazy" />
	                  </a>
	                </div>
	                <div v-if="m.attachments?.some((a: any) => a.kind === 'file')" class="fileChips">
	                  <a
	                    v-for="(a, idx) in (m.attachments ?? []).filter((x: any) => x.kind === 'file')"
	                    :key="`${idx}-${a.url}`"
	                    class="fileChip"
	                    :href="a.url"
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

            <div v-if="sending" class="bubble assistant">
              <div class="bubbleMeta">
                <span class="who">AI</span>
              </div>
              <div class="typing">
                <span class="spinner" />
                <div class="typingText">
                  <div>思考中… {{ sendingElapsed }}s</div>
                  <div v-if="sendingElapsed >= 10" class="subtle">模型计算较慢，可继续等待或取消</div>
                </div>
                <button class="ghostBtn tinyBtn" type="button" @click="cancelSend">取消</button>
              </div>
            </div>

            <button v-if="showScrollToBottom" class="ghostBtn iconBtn scrollToBottom" type="button" @click="scrollToBottom(true)">
              <span class="msIcon btnIcon" aria-hidden="true">arrow_downward</span>
              <span>回到底部</span>
            </button>
          </div>

	          <div class="composer">
	            <div v-if="pendingImages.length || pendingFiles.length" class="composerAttachments">
	              <div v-for="img in pendingImages" :key="img.file_id" class="attThumb">
	                <a :href="img.url" target="_blank" rel="noreferrer">
	                  <img :src="img.url" :alt="img.filename" loading="lazy" />
	                </a>
	                <button
	                  class="attRemove"
	                  type="button"
	                  :disabled="sending || uploadingImages || uploadingFiles"
	                  @click="removePendingImage(img.file_id)"
	                >
	                  ×
	                </button>
	              </div>
	              <div v-for="f in pendingFiles" :key="f.file_id" class="attFile">
	                <a class="fileChip" :href="f.url" target="_blank" rel="noreferrer">
	                  <span class="fileChipIcon" :data-kind="_fileKindFromId(f.filename)">
	                    {{ _fileKindFromId(f.filename).toUpperCase() }}
	                  </span>
	                  <span class="fileChipName">{{ f.filename }}</span>
	                </a>
	                <button
	                  class="fileRemove"
	                  type="button"
	                  :disabled="sending || uploadingFiles || uploadingImages"
	                  @click="removePendingFile(f.file_id)"
	                >
	                  ×
	                </button>
	              </div>
	            </div>
	            <input ref="imagePickerRef" class="hiddenFileInput" type="file" accept="image/*" multiple @change="onPickImages" />
	            <input ref="filePickerRef" class="hiddenFileInput" type="file" multiple @change="onPickFiles" />
            <textarea
              ref="composerInputRef"
              v-model="input"
              class="composerInput"
              placeholder="写下你的需求…（支持 Markdown，可拖拽/粘贴图片与文件）"
              @keydown="onComposerKeydown"
              @paste="onComposerPaste"
            />
	            <div class="composerActions">
	              <div class="subtle">提供商={{ provider }} · 角色={{ role }}</div>
	              <div class="composerButtons">
                <button class="ghostBtn" :disabled="sending || uploadingImages || uploadingFiles" type="button" @click="pickImages">
                  <span class="msIcon btnIcon" aria-hidden="true">imagesmode</span>
                  <span>{{ uploadingImages ? "上传中…" : "上传图片" }}</span>
                </button>
                <button class="ghostBtn" :disabled="sending || uploadingImages || uploadingFiles" type="button" @click="pickFiles">
                  <span class="msIcon btnIcon" aria-hidden="true">upload_file</span>
                  <span>{{ uploadingFiles ? "上传中…" : "上传文件" }}</span>
                </button>
                <button
                  class="primaryBtn"
                  :disabled="sending || uploadingImages || uploadingFiles || (!input.trim() && pendingImages.length === 0 && pendingFiles.length === 0)"
                  type="button"
                  @click="send"
                >
                  <span class="msIcon btnIcon" aria-hidden="true">send</span>
                  <span>发送</span>
                </button>
              </div>
            </div>
            <div v-if="uploadError" class="error">{{ uploadError }}</div>
          </div>
        </main>

        <aside v-if="showRight" class="previewSide">
          <section class="card previewCard">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">dock_to_right</span>预览</h3>
              <button v-if="activePreview" class="ghostBtn iconBtn" type="button" @click="activePreview = null">
                <span class="msIcon btnIcon" aria-hidden="true">ink_eraser</span>
                <span>清空</span>
              </button>
            </div>

            <div class="previewBody">
              <div v-if="activePreview?.kind === 'ppt' && activePpt" class="pptPreview">
                <div class="pptPreviewHead">
                  <div class="pptPreviewTitle">
                    PPT 预览（共
                    {{
                      activePpt.slideImageUrls?.length
                        ? activePpt.slideImageUrls.length
                        : (activePpt.slides.length ?? 0) + 1
                    }}
                    页）
                  </div>
                  <div v-if="activePpt.downloadUrl" class="protoActions">
                    <a class="ghostBtn" :href="activePpt.downloadUrl" target="_blank" rel="noreferrer">下载</a>
                  </div>
                </div>
                <div class="pptSlides">
                  <template v-if="activePpt.slideImageUrls?.length">
                    <div v-for="(img, idx) in activePpt.slideImageUrls" :key="`${idx}-${img}`" class="pptSlideCard pptCover pptCoverReal">
                      <div class="pptSlideNo">{{ idx + 1 }}</div>
                      <img class="pptCoverImage" :src="img" :alt="`PPT 第 ${idx + 1} 页`" loading="lazy" referrerpolicy="no-referrer" />
                      <div class="pptRealBadge">真实渲染</div>
                    </div>
                  </template>
                  <template v-else>
                    <div class="pptSlideCard pptCover" :class="{ pptCoverReal: !!activePpt.coverImageUrl }">
                      <div class="pptSlideNo">1</div>
                      <img
                        v-if="activePpt.coverImageUrl"
                        class="pptCoverImage"
                        :src="activePpt.coverImageUrl"
                        alt="PPT 封面预览"
                        loading="lazy"
                        referrerpolicy="no-referrer"
                      />
                      <div v-else class="pptCoverTitle">{{ activePpt.title }}</div>
                      <div v-if="activePpt.coverImageUrl" class="pptRealBadge">真实渲染</div>
                    </div>
                    <div v-for="(s, idx) in activePpt.slides" :key="`${idx}-${s.title}`" class="pptSlideCard">
                      <div class="pptSlideNo">{{ idx + 2 }}</div>
                      <div class="pptSlideTitle">{{ s.title }}</div>
                      <ul class="pptBullets">
                        <li v-for="(b, j) in s.bullets.slice(0, 6)" :key="j">{{ b }}</li>
                        <li v-if="s.bullets.length > 6" class="pptMore">…</li>
                      </ul>
                    </div>
                  </template>
                </div>
              </div>

              <div v-else-if="activePreview?.kind === 'doc' && activeDoc" class="pptPreview">
                <div class="pptPreviewHead">
                  <div class="pptPreviewTitle">
                    {{ activeDoc.kind === "pdf" ? "PDF" : "Word" }} 预览（共 {{ activeDoc.pageImageUrls?.length ?? 0 }} 页）
                  </div>
                  <div class="protoActions">
                    <a v-if="activeDoc.downloadUrl" class="ghostBtn" :href="activeDoc.downloadUrl" target="_blank" rel="noreferrer">下载</a>
                    <a v-if="activeDoc.previewUrl" class="ghostBtn" :href="activeDoc.previewUrl" target="_blank" rel="noreferrer">新窗口打开</a>
                  </div>
                </div>
                <template v-if="activeDoc.pageImageUrls?.length">
                  <div class="pageStack">
                    <div v-for="(img, idx) in activeDoc.pageImageUrls" :key="`${idx}-${img}`" class="pageStackItem">
                      <div class="pptSlideNo">{{ idx + 1 }}</div>
                      <img class="pageStackImage" :src="img" :alt="`${activeDoc.kind.toUpperCase()} 第 ${idx + 1} 页`" loading="lazy" referrerpolicy="no-referrer" />
                      <div class="pptRealBadge">真实渲染</div>
                    </div>
                  </div>
                </template>
                <div v-else class="subtle" style="padding: 12px;">暂无可视化预览，请下载查看。</div>
              </div>

              <div v-else-if="activePreview?.kind === 'quote' && activeQuote" class="quotePreview">
                <div class="quotePreviewHead">
                  <div class="quotePreviewTitle">报价单预览（{{ activeQuote.kind.toUpperCase() }}）</div>
                  <div class="quoteMeta">
                    <span>供方：{{ activeQuote.seller }}</span>
                    <span>需方：{{ activeQuote.buyer }}</span>
                    <span>合计：{{ formatMoney(activeQuote.total) }} {{ activeQuote.currency }}</span>
                  </div>
                </div>
                <div class="quoteBody">
                  <table class="quoteTable">
                    <thead>
                      <tr>
                        <th>名称</th>
                        <th>数量</th>
                        <th>单位</th>
                        <th>单价</th>
                        <th>小计</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(it, idx) in activeQuote.items" :key="`${idx}-${it.name}`">
                        <td class="qName">{{ it.name }}</td>
                        <td class="qNum">{{ it.quantity }}</td>
                        <td class="qUnit">{{ it.unit ?? "项" }}</td>
                        <td class="qNum">{{ formatMoney(it.unit_price) }}</td>
                        <td class="qNum">{{ formatMoney(it.quantity * it.unit_price) }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <div v-if="activeQuote.note" class="quoteNote">备注：{{ activeQuote.note }}</div>
                </div>
              </div>

              <div v-else-if="activePreview?.kind === 'sheet' && activeSheet" class="protoPreview">
                <div class="protoPreviewHead">
                  <div class="protoPreviewTitle">Excel 预览：{{ activeSheet.filename }}</div>
                  <div class="protoActions">
                    <a class="ghostBtn" :href="activeSheet.downloadUrl" target="_blank" rel="noreferrer">下载</a>
                    <a v-if="activeSheet.previewUrl" class="ghostBtn" :href="activeSheet.previewUrl" target="_blank" rel="noreferrer">新窗口打开</a>
                  </div>
                </div>
                <template v-if="activeSheet.pageImageUrls?.length">
                  <div class="pageStack">
                    <div v-for="(img, idx) in activeSheet.pageImageUrls" :key="`${idx}-${img}`" class="pageStackItem">
                      <div class="pptSlideNo">{{ idx + 1 }}</div>
                      <img class="pageStackImage" :src="img" :alt="`Excel 第 ${idx + 1} 页`" loading="lazy" referrerpolicy="no-referrer" />
                      <div class="pptRealBadge">真实渲染</div>
                    </div>
                  </div>
                </template>
                <iframe
                  v-else-if="activeSheet.previewUrl"
                  class="protoFrame"
                  :src="activeSheet.previewUrl"
                  loading="lazy"
                  sandbox="allow-same-origin"
                  referrerpolicy="no-referrer"
                />
                <div v-else class="subtle">暂无可视化预览，请下载查看。</div>
              </div>

              <div v-else-if="activePreview?.kind === 'proto' && activeProto" class="protoPreview">
                <div class="protoPreviewHead">
                  <div class="protoPreviewTitle">原型预览：{{ activeProto.project_name }}</div>
                  <div class="protoActions">
                    <a class="ghostBtn" :href="activeProto.preview_url" target="_blank" rel="noreferrer">新窗口打开</a>
                    <button class="ghostBtn" type="button" @click="copyToClipboard(activeProto.preview_url)">
                      复制链接
                    </button>
                  </div>
                </div>
                <iframe
                  class="protoFrame"
                  :src="activeProto.preview_url"
                  loading="lazy"
                  sandbox="allow-same-origin"
                  referrerpolicy="no-referrer"
                />
              </div>

              <div v-else-if="activePreview?.kind === 'readme'" class="readmePreview">
                <div class="readmePreviewHead">
                  <div>
                    <div class="readmePreviewTitle">README：{{ activeReadme?.title ?? "README" }}</div>
                    <div class="subtle mono">
                      {{ activeReadme?.sourceLabel ?? "工作区" }}{{ activeReadme?.relPath ? ` · ${activeReadme.relPath}` : "" }}
                    </div>
                  </div>
                  <div class="protoActions">
                    <button class="ghostBtn" type="button" @click="openProjectReadme(activePreview.projectId)">刷新</button>
                  </div>
                </div>
                <div v-if="activeReadmeBusy" class="subtle">正在读取 README…</div>
                <div v-else-if="activeReadmeError" class="error">{{ activeReadmeError }}</div>
                <div v-else-if="!activeReadme" class="subtle">未找到 README。</div>
                <div v-else class="md readmeMarkdown" v-html="renderMarkdown(activeReadme.content)" />
                <div v-if="activeReadme?.truncated" class="subtle readmeTruncate">内容过长已截断，可本地打开查看更多。</div>
              </div>

              <div v-else-if="activePreview?.kind === 'images' && activeImages.length" class="attachmentGrid">
                <a
                  v-for="(a, idx) in activeImages"
                  :key="`${idx}-${a.url}`"
                  class="attachmentLink"
                  :href="a.url"
                  target="_blank"
                  rel="noreferrer"
                >
                  <img :src="a.url" :alt="a.filename ?? 'image'" loading="lazy" />
                </a>
              </div>

              <div v-else-if="activePreview?.kind === 'files' && activeFileDownloads.length" class="filePreview">
                <div class="filePreviewHead">
                  <div class="filePreviewTitle">文件（{{ activeFileDownloads.length }}）</div>
                </div>
                <div class="fileList">
                  <div v-for="d in activeFileDownloads" :key="d.absolute" class="fileItem">
                    <div class="fileIcon" :data-kind="_fileKindFromId(_fileIdFromDownload(d.absolute))">
                      {{ _fileKindFromId(_fileIdFromDownload(d.absolute)).toUpperCase() }}
                    </div>
                    <div class="fileMeta">
                      <div class="fileName mono">{{ _fileIdFromDownload(d.absolute) }}</div>
                      <div class="subtle mono">{{ d.absolute }}</div>
                    </div>
                    <div class="fileActions">
                      <a class="primaryBtn" :href="d.absolute" target="_blank" rel="noreferrer">下载</a>
                      <button class="ghostBtn" type="button" @click="copyToClipboard(d.absolute)">复制</button>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="subtle">暂无预览：生成 PPT/报价单/原型、上传图片或生成文件后会显示在这里。</div>
            </div>
          </section>
        </aside>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue"

export default defineComponent({
  name: "SessionMainDomain",
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
