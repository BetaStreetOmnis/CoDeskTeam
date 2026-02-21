<template>
            <section v-if="leftNavSection === 'workspace'" class="card workspacePanelCard">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">widgets</span>工作台</h3>
              <button class="ghostBtn" :disabled="teamProjectsBusy || teamSettingsBusy" type="button" @click="refreshWorkspace">刷新</button>
            </div>
            <label class="select wide">
              <span class="label">项目</span>
              <select v-model.number="activeProjectId" @change="onSwitchProject">
                <option :value="0">{{ teamWorkspacePath ? "团队工作区（默认）" : "默认（AISTAFF_WORKSPACE）" }}</option>
                <option v-for="p in teamProjects" :key="`quick-project-${p.id}`" :value="p.id" :disabled="!p.enabled">
                  {{ p.name }}{{ p.enabled ? "" : "（禁用）" }}
                </option>
              </select>
            </label>
            <div class="subtle mono pathLine" :title="activeWorkspacePath">{{ activeWorkspacePath }}</div>
            <div class="tabs workspacePanelTabs">
              <button class="tab" :class="{ active: workspacePanel === 'projects' }" type="button" @click="workspacePanel = 'projects'">
                项目维护
              </button>
              <button class="tab" :class="{ active: workspacePanel === 'requirements' }" type="button" @click="workspacePanel = 'requirements'">
                需求维护
              </button>
              <button class="tab" :class="{ active: workspacePanel === 'capabilities' }" type="button" @click="workspacePanel = 'capabilities'">
                能力开关
              </button>
              <button class="tab" :class="{ active: workspacePanel === 'chatbi' }" type="button" @click="workspacePanel = 'chatbi'">
                智能问数
              </button>
              <button class="tab" :class="{ active: workspacePanel === 'browser' }" type="button" @click="workspacePanel = 'browser'">
                浏览器
              </button>
            </div>
            <div v-if="teamSettingsError" class="error">{{ teamSettingsError }}</div>
            <div v-else-if="teamProjectsError" class="error">{{ teamProjectsError }}</div>
          </section>

          <section v-if="leftNavSection === 'workspace' && workspacePanel === 'projects'" class="card">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">folder_open</span>项目维护列表</h3>
              <button class="ghostBtn" :disabled="teamProjectsBusy" type="button" @click="refreshTeamProjects">刷新</button>
            </div>
            <div class="row compactRow wrapRow">
              <input v-model="projectSearch" class="input" placeholder="搜索项目名称 / 路径…" />
              <button v-if="projectSearch.trim()" class="ghostBtn" type="button" @click="projectSearch = ''">清空</button>
              <button v-if="canEditTeamProjects" class="ghostBtn" type="button" @click="openProjectManagerForNewProject">+ 新建项目</button>
            </div>
            <div v-if="teamProjectsBusy" class="subtle">正在加载项目…</div>
            <div v-else class="historyList workspaceList">
              <div class="historyItem workspaceListItem" :class="{ active: activeProjectId === 0, projectTreeExpanded: projectTreeExpandedById[0] }">
                <div class="historyItemMain workspaceListMain">
                  <div class="historyTitle">{{ teamWorkspacePath ? "团队工作区（默认）" : "默认工作区（AISTAFF_WORKSPACE）" }}</div>
                  <div class="historyMetaRow">
                    <span class="metaPill">默认入口</span>
                    <span>{{ teamWorkspacePath ? "团队自定义路径" : "服务端默认路径" }}</span>
                  </div>
                  <div
                    class="subtle mono pathLine"
                    :title="activeWorkspacePath || teamWorkspacePath || '服务端 AISTAFF_WORKSPACE（默认）'"
                  >
                    {{ activeWorkspacePath || teamWorkspacePath || "服务端 AISTAFF_WORKSPACE（默认）" }}
                  </div>
                </div>
                <div class="historyActions">
                  <button class="ghostBtn" :disabled="activeProjectId === 0" type="button" @click="switchWorkspaceProject(0)">切换</button>
                  <button class="ghostBtn" type="button" @click="toggleProjectTree(0)">
                    {{ projectTreeExpandedById[0] ? "收起目录" : "目录" }}
                  </button>
                  <button class="ghostBtn" :disabled="readmeBusyByProjectId[0]" type="button" @click="openProjectReadme(0)">
                    {{ readmeBusyByProjectId[0] ? "读取中" : "README" }}
                  </button>
                  <button v-if="canEditTeamProjects" class="ghostBtn" type="button" @click="openProjectManager">维护</button>
                </div>

                <div v-if="projectTreeExpandedById[0]" class="projectTreePanel">
                  <div v-if="projectTreeBusyById[0]" class="subtle">正在读取目录…</div>
                  <div v-else-if="projectTreeErrorById[0]" class="error">{{ projectTreeErrorById[0] }}</div>
                  <div v-else-if="flattenProjectTree(0).length === 0" class="subtle">目录为空。</div>
                  <ul v-else class="projectTreeList">
                    <li v-for="row in flattenProjectTree(0)" :key="row.key" class="projectTreeRow">
                      <div
                        class="projectTreeRowInner"
                        :data-level="row.level"
                        :data-node-type="row.node.node_type"
                        :style="{ paddingLeft: `${row.level * 16 + 8}px`, '--tree-indent': `${row.level * 16 + 8}px` }"
                      >
                        <button
                          v-if="row.node.node_type === 'dir'"
                          class="treeToggleBtn"
                          :disabled="!row.node.has_children"
                          type="button"
                          @click="toggleProjectTreeFolder(0, row.node)"
                        >
                          <span class="msIcon btnIcon" aria-hidden="true">
                            {{ row.node.has_children ? (isProjectTreeFolderOpen(0, row.node.rel_path) ? "expand_more" : "chevron_right") : "chevron_right" }}
                          </span>
                        </button>
                        <span v-else class="treeTogglePlaceholder"></span>
                        <span class="msIcon treeNodeIcon" aria-hidden="true">{{ row.node.node_type === "dir" ? "folder" : "description" }}</span>
                        <span class="treeNodeName">{{ row.node.name }}</span>
                        <span v-if="row.node.node_type === 'dir' && isProjectTreeFolderBusy(0, row.node.rel_path)" class="subtle">加载中…</span>
                      </div>
                    </li>
                  </ul>
                </div>
              </div>

              <div
                v-for="p in filteredTeamProjects"
                :key="p.id"
                class="historyItem workspaceListItem"
                :class="{ active: activeProjectId === p.id, projectTreeExpanded: projectTreeExpandedById[p.id] }"
              >
                <div class="historyItemMain workspaceListMain">
                  <div class="historyTitle">{{ p.name }}{{ p.enabled ? "" : "（禁用）" }}</div>
                  <div class="historyMetaRow">
                    <span class="metaPill">{{ p.slug }}</span>
                    <span>{{ formatIsoTime(p.updated_at) }}</span>
                  </div>
                  <div class="subtle mono pathLine" :title="p.path">{{ p.path }}</div>
                </div>
                <div class="historyActions">
                  <button
                    class="ghostBtn"
                    :disabled="activeProjectId === p.id || !p.enabled"
                    type="button"
                    @click="switchWorkspaceProject(p.id)"
                  >
                    切换
                  </button>
                  <button class="ghostBtn" type="button" @click="toggleProjectTree(p.id)">
                    {{ projectTreeExpandedById[p.id] ? "收起目录" : "目录" }}
                  </button>
                  <button class="ghostBtn" :disabled="readmeBusyByProjectId[p.id]" type="button" @click="openProjectReadme(p.id)">
                    {{ readmeBusyByProjectId[p.id] ? "读取中" : "README" }}
                  </button>
                  <button
                    v-if="canEditTeamProjects"
                    class="ghostBtn"
                    type="button"
                    @click="openProjectManagerForProject(p)"
                  >
                    维护
                  </button>
                </div>

                <div v-if="projectTreeExpandedById[p.id]" class="projectTreePanel">
                  <div v-if="projectTreeBusyById[p.id]" class="subtle">正在读取目录…</div>
                  <div v-else-if="projectTreeErrorById[p.id]" class="error">{{ projectTreeErrorById[p.id] }}</div>
                  <div v-else-if="flattenProjectTree(p.id).length === 0" class="subtle">目录为空。</div>
                  <ul v-else class="projectTreeList">
                    <li v-for="row in flattenProjectTree(p.id)" :key="row.key" class="projectTreeRow">
                      <div
                        class="projectTreeRowInner"
                        :data-level="row.level"
                        :data-node-type="row.node.node_type"
                        :style="{ paddingLeft: `${row.level * 16 + 8}px`, '--tree-indent': `${row.level * 16 + 8}px` }"
                      >
                        <button
                          v-if="row.node.node_type === 'dir'"
                          class="treeToggleBtn"
                          :disabled="!row.node.has_children"
                          type="button"
                          @click="toggleProjectTreeFolder(p.id, row.node)"
                        >
                          <span class="msIcon btnIcon" aria-hidden="true">
                            {{ row.node.has_children ? (isProjectTreeFolderOpen(p.id, row.node.rel_path) ? "expand_more" : "chevron_right") : "chevron_right" }}
                          </span>
                        </button>
                        <span v-else class="treeTogglePlaceholder"></span>
                        <span class="msIcon treeNodeIcon" aria-hidden="true">{{ row.node.node_type === "dir" ? "folder" : "description" }}</span>
                        <span class="treeNodeName">{{ row.node.name }}</span>
                        <span v-if="row.node.node_type === 'dir' && isProjectTreeFolderBusy(p.id, row.node.rel_path)" class="subtle">加载中…</span>
                      </div>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
            <div v-if="!teamProjectsBusy && filteredTeamProjects.length === 0" class="subtle">没有匹配的项目。</div>
            <div v-if="teamProjectsError" class="error">{{ teamProjectsError }}</div>
          </section>

          <section v-if="leftNavSection === 'workspace' && workspacePanel === 'requirements'" class="card">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">assignment</span>需求维护列表</h3>
              <div class="cardHeadActions">
                <button class="ghostBtn" :disabled="teamRequirementsBusy" type="button" @click="refreshTeamRequirements">刷新</button>
                <button v-if="canEditTeamRequirements" class="ghostBtn" type="button" @click="newTeamRequirement">+ 新建</button>
              </div>
            </div>

            <div class="row compactRow wrapRow">
              <input v-model="requirementSearch" class="input" placeholder="搜索需求标题 / 描述 / 来源团队…" />
              <label class="select compactSelect">
                <span class="label">状态</span>
                <select v-model="requirementStatusFilter">
                  <option value="">全部</option>
                  <option value="incoming">新交付</option>
                  <option value="todo">待处理</option>
                  <option value="in_progress">处理中</option>
                  <option value="done">已完成</option>
                  <option value="blocked">阻塞</option>
                </select>
              </label>
              <label class="select compactSelect">
                <span class="label">优先级</span>
                <select v-model="requirementPriorityFilter">
                  <option value="">全部</option>
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                  <option value="urgent">紧急</option>
                </select>
              </label>
              <button
                v-if="requirementSearch.trim() || requirementStatusFilter || requirementPriorityFilter"
                class="ghostBtn"
                type="button"
                @click="resetRequirementFilters"
              >
                清空筛选
              </button>
            </div>

            <div class="row compactRow requirementStatsRow">
              <span class="metaPill">总计 {{ requirementStats.total }}</span>
              <span class="metaPill reqStatusPill" data-status="incoming">新交付 {{ requirementStats.incoming }}</span>
              <span class="metaPill reqStatusPill" data-status="todo">待处理 {{ requirementStats.todo }}</span>
              <span class="metaPill reqStatusPill" data-status="in_progress">处理中 {{ requirementStats.in_progress }}</span>
              <span class="metaPill reqStatusPill" data-status="done">已完成 {{ requirementStats.done }}</span>
              <span class="metaPill reqStatusPill" data-status="blocked">阻塞 {{ requirementStats.blocked }}</span>
            </div>

            <div v-if="teamRequirementsBusy" class="subtle">正在加载需求…</div>
            <div v-else-if="filteredTeamRequirements.length === 0" class="subtle">
              {{ teamRequirements.length === 0 ? "暂无需求，可等待外部团队交付或手动新建。" : "没有匹配的需求，请调整筛选条件。" }}
            </div>
            <div v-else class="historyList workspaceList requirementsList">
              <div
                v-for="item in filteredTeamRequirements"
                :key="item.id"
                class="historyItem workspaceListItem requirementListItem"
                :class="{ active: selectedTeamRequirementId === item.id }"
              >
                <button class="historyItemMain workspaceListMain" type="button" @click="selectTeamRequirement(item)">
                  <div class="historyTitle">{{ item.title }}</div>
                  <div class="historyMetaRow">
                    <span class="metaPill reqStatusPill" :data-status="item.status">{{ requirementStatusLabel(item.status) }}</span>
                    <span class="metaPill reqPriorityPill" :data-priority="item.priority">{{ requirementPriorityLabel(item.priority) }}</span>
                    <span class="metaPill">{{ projectNameFromId(item.project_id) }}</span>
                  </div>
	                  <div v-if="item.description" class="historySnippet">{{ item.description }}</div>
	                  <div class="historyMetaRow">
	                    <span>{{ formatIsoTime(item.updated_at) }}</span>
	                    <span v-if="item.delivery?.from_team_name || item.source_team">来源：{{ item.delivery?.from_team_name || item.source_team }}</span>
	                  </div>
	                </button>
	                <div class="historyActions">
	                  <button class="ghostBtn" type="button" @click="selectTeamRequirement(item)">编辑</button>
	                  <button
	                    v-if="canEditTeamRequirements && item.status === 'incoming' && item.delivery?.state === 'pending'"
	                    class="ghostBtn"
	                    :disabled="teamRequirementsBusy"
	                    type="button"
	                    @click="acceptRequirementDelivery(item)"
	                  >
	                    接收
	                  </button>
	                  <button
	                    v-if="canEditTeamRequirements && item.status === 'incoming' && item.delivery?.state === 'pending'"
	                    class="ghostBtn"
	                    :disabled="teamRequirementsBusy"
	                    type="button"
	                    @click="rejectRequirementDelivery(item)"
	                  >
	                    拒绝
	                  </button>
	                  <button
	                    v-if="canEditTeamRequirements"
	                    class="ghostBtn"
	                    :disabled="teamRequirementsBusy || item.status === 'in_progress' || item.delivery?.state === 'pending'"
	                    type="button"
	                    @click="quickSetRequirementStatus(item, 'in_progress')"
	                  >
	                    开始
	                  </button>
	                  <button
	                    v-if="canEditTeamRequirements"
	                    class="ghostBtn"
	                    :disabled="teamRequirementsBusy || item.status === 'done' || item.delivery?.state === 'pending'"
	                    type="button"
	                    @click="quickSetRequirementStatus(item, 'done')"
	                  >
	                    完成
	                  </button>
	                </div>
	              </div>
            </div>

            <div
              v-if="selectedTeamRequirementId"
              class="tabBody requirementEditor"
              @keydown.ctrl.s.prevent="saveTeamRequirement"
              @keydown.meta.s.prevent="saveTeamRequirement"
            >
              <div class="subtle shortcutHint">快捷键：Ctrl/⌘ + S 保存当前需求</div>

	              <label class="select wide">
	                <span class="label">所属项目</span>
	                <select v-model.number="teamRequirementForm.project_id" :disabled="!canEditTeamRequirements">
	                  <option :value="0">未归属（默认工作区）</option>
	                  <option v-for="p in teamProjects" :key="`req-project-${p.id}`" :value="p.id">{{ p.name }}</option>
	                </select>
	              </label>

	              <div class="row" v-if="selectedTeamRequirementId === 'new'">
	                <label class="select wide">
	                  <span class="label">交付到</span>
	                  <select
	                    v-model.number="teamRequirementForm.delivery_target_team_id"
	                    :disabled="!canEditTeamRequirements || selectedTeamRequirementId !== 'new'"
	                  >
	                    <option :value="0">本团队（直接创建）</option>
	                    <option
	                      v-for="t in me?.teams || []"
	                      :key="`req-delivery-${t.id}`"
	                      :value="t.id"
	                      :disabled="t.id === me?.active_team?.id"
	                    >
	                      {{ t.name }}（#{{ t.id }}）
	                    </option>
	                  </select>
	                </label>
	              </div>

	              <div class="row">
	                <input
	                  v-model="teamRequirementForm.source_team"
	                  class="input"
	                  :disabled="!canEditTeamRequirements || (selectedTeamRequirementId === 'new' && teamRequirementForm.delivery_target_team_id > 0)"
	                  placeholder="来源团队（外部交付会自动填充）"
	                />
	              </div>

              <div class="row">
                <input
                  v-model="teamRequirementForm.title"
                  class="input"
                  :disabled="!canEditTeamRequirements"
                  placeholder="需求标题"
                />
              </div>

              <div class="row requirementSelectRow">
                <label class="select wide">
                  <span class="label">状态</span>
                  <select v-model="teamRequirementForm.status" :disabled="!canEditTeamRequirements">
                    <option value="incoming">新交付</option>
                    <option value="todo">待处理</option>
                    <option value="in_progress">处理中</option>
                    <option value="done">已完成</option>
                    <option value="blocked">阻塞</option>
                  </select>
                </label>
                <label class="select wide">
                  <span class="label">优先级</span>
                  <select v-model="teamRequirementForm.priority" :disabled="!canEditTeamRequirements">
                    <option value="low">低</option>
                    <option value="medium">中</option>
                    <option value="high">高</option>
                    <option value="urgent">紧急</option>
                  </select>
                </label>
              </div>

              <textarea
                v-model="teamRequirementForm.description"
                class="textarea requirementTextarea"
                :disabled="!canEditTeamRequirements"
                placeholder="需求说明 / 验收标准 / 附件说明（Markdown）"
              />

              <div class="subtle" v-if="selectedTeamRequirement">
                项目：{{ projectNameFromId(selectedTeamRequirement.project_id) }} · 更新时间：{{ formatIsoTime(selectedTeamRequirement.updated_at) }}
              </div>

              <div class="row requirementActionRow">
                <button
                  class="primaryBtn"
                  :disabled="teamRequirementsBusy || !canEditTeamRequirements"
                  type="button"
                  @click="saveTeamRequirement"
                >
                  保存
                </button>
                <button
                  v-if="selectedTeamRequirementId !== 'new'"
                  class="ghostBtn"
                  :disabled="teamRequirementsBusy || !canEditTeamRequirements"
                  type="button"
                  @click="removeTeamRequirement"
                >
                  删除
                </button>
              </div>

              <div v-if="teamRequirementsError" class="error">{{ teamRequirementsError }}</div>
            </div>
          </section>

          <section v-if="leftNavSection === 'workspace' && workspacePanel === 'capabilities'" class="card">
            <div class="cardHead capHead">
              <div class="capHeadMain">
                <h3><span class="msIcon h3Icon" aria-hidden="true">admin_panel_settings</span>能力开关</h3>
                <div class="subtle">服务端 .env 是能力上限，前端档位是请求下限</div>
                <div v-if="!canEditTeamSkills" class="subtle capLockHint">仅管理员可启用高危能力</div>
                <div v-else-if="securityPreset !== 'custom'" class="subtle capLockHint">切换为 custom 后可手动开关</div>
              </div>
              <div class="capStatus">
                <span class="capBadge">{{ securityPresetLabel }}</span>
                <span class="capBadge" :class="enableShell ? 'on' : 'off'">shell {{ enableShell ? "on" : "off" }}</span>
                <span class="capBadge" :class="enableWrite ? 'on' : 'off'">write {{ enableWrite ? "on" : "off" }}</span>
                <span class="capBadge" :class="enableBrowser ? 'on' : 'off'">browser {{ enableBrowser ? "on" : "off" }}</span>
              </div>
            </div>

            <div class="capGrid">
              <div class="capBlock">
                <label class="select wide">
                  <span class="label">Agent 档案</span>
                  <select v-model="selectedAgentProfileId" @change="applyAgentProfile(selectedAgentProfileId)">
                    <option value="custom">自定义（保持当前）</option>
                    <option v-for="p in agentProfiles" :key="p.id" :value="p.id">{{ p.name }} · {{ p.description }}</option>
                  </select>
                </label>
                <div class="capBlockDesc">一键套用角色、语气、工具档位</div>
              </div>
              <div class="capBlock">
                <label class="select wide">
                  <span class="label">安全档位</span>
                  <select v-model="securityPreset" :disabled="!canEditTeamSkills">
                    <option value="safe">safe（仅读）</option>
                    <option value="standard">standard（可写，不可 shell/browser）</option>
                    <option value="power">power（全能力）</option>
                    <option value="custom">custom（手动）</option>
                  </select>
                </label>
                <div class="capPresetTips">
                  <span class="capPreset">safe 只读</span>
                  <span class="capPreset">standard 可写</span>
                  <span class="capPreset">power 全能力</span>
                  <span class="capPreset">custom 手动</span>
                </div>
              </div>
            </div>

            <div class="capToggleList">
              <label class="capToggleItem" :class="{ disabled: dangerousTogglesLocked }">
                <div class="capToggleMain">
                  <input v-model="enableShell" type="checkbox" :disabled="dangerousTogglesLocked" />
                  <div class="capToggleText">
                    <div class="capToggleTitle">Shell 运行</div>
                    <div class="capToggleDesc">允许运行本机命令（高危）</div>
                  </div>
                </div>
                <div class="capToggleTags">
                  <span class="tag danger">高危</span>
                  <span class="capState" :class="enableShell ? 'on' : 'off'">{{ enableShell ? "开启" : "关闭" }}</span>
                </div>
              </label>
              <label class="capToggleItem" :class="{ disabled: dangerousTogglesLocked }">
                <div class="capToggleMain">
                  <input v-model="enableWrite" type="checkbox" :disabled="dangerousTogglesLocked" />
                  <div class="capToggleText">
                    <div class="capToggleTitle">文件写入</div>
                    <div class="capToggleDesc">允许写入本地文件系统（高危）</div>
                  </div>
                </div>
                <div class="capToggleTags">
                  <span class="tag danger">高危</span>
                  <span class="capState" :class="enableWrite ? 'on' : 'off'">{{ enableWrite ? "开启" : "关闭" }}</span>
                </div>
              </label>
              <label class="capToggleItem" :class="{ disabled: dangerousTogglesLocked }">
                <div class="capToggleMain">
                  <input v-model="enableBrowser" type="checkbox" :disabled="dangerousTogglesLocked" />
                  <div class="capToggleText">
                    <div class="capToggleTitle">浏览器访问</div>
                    <div class="capToggleDesc">允许联网检索与页面抓取（高危）</div>
                  </div>
                </div>
                <div class="capToggleTags">
                  <span class="tag danger">高危</span>
                  <span class="capState" :class="enableBrowser ? 'on' : 'off'">{{ enableBrowser ? "开启" : "关闭" }}</span>
                </div>
              </label>
              <label class="capToggleItem" :class="{ disabled: dangerousBypassLocked }">
                <div class="capToggleMain">
                  <input v-model="enableDangerous" type="checkbox" :disabled="dangerousBypassLocked" />
                  <div class="capToggleText">
                    <div class="capToggleTitle">无沙箱模式</div>
                    <div class="capToggleDesc">允许访问真实系统环境，仅 Codex</div>
                  </div>
                </div>
                <div class="capToggleTags">
                  <span class="tag danger">高危</span>
                  <span class="capState" :class="effectiveDangerous ? 'on' : 'off'">{{ effectiveDangerous ? "开启" : "关闭" }}</span>
                </div>
              </label>
              <label class="capToggleItem">
                <div class="capToggleMain">
                  <input v-model="showReasoning" type="checkbox" />
                  <div class="capToggleText">
                    <div class="capToggleTitle">思路摘要</div>
                    <div class="capToggleDesc">在聊天气泡内展示简短思路</div>
                  </div>
                </div>
                <div class="capToggleTags">
                  <span class="tag">显示</span>
                  <span class="capState" :class="showReasoning ? 'on' : 'off'">{{ showReasoning ? "开启" : "关闭" }}</span>
                </div>
              </label>
            </div>

            <div class="capFoot">
              <div class="subtle" v-if="provider !== 'codex'">无沙箱仅 Codex 可用</div>
              <div class="subtle" v-else>无沙箱需服务端开启 AISTAFF_CODEX_ALLOW_DANGEROUS=1</div>
            </div>
          </section>

          <section v-if="leftNavSection === 'skills'" ref="builtinSkillsCard" class="card">
            <div class="cardHead">
              <div>
                <h3><span class="msIcon h3Icon" aria-hidden="true">auto_awesome</span>内置技能模板中心</h3>
                <div class="subtle">可视化编辑模板参数，生成后直接交付</div>
              </div>
              <div class="cardHeadActions">
                <button class="ghostBtn" type="button" @click="openChatbi">
                  <span class="msIcon btnIcon" aria-hidden="true">query_stats</span>
                  <span>智能问数</span>
                </button>
                <button class="ghostBtn" type="button" @click="scrollToTeamSkills">
                  <span class="msIcon btnIcon" aria-hidden="true">group_work</span>
                  <span>团队技能</span>
                </button>
              </div>
            </div>

            <div v-if="skills.length" class="skillCatalog">
              <button
                v-for="s in skills"
                :key="s.id"
                class="skillCatalogItem"
                :class="{ active: selectedSkillId === s.id }"
                type="button"
                @click="selectedSkillId = s.id"
              >
                <div class="skillCatalogTitle">{{ s.name }}</div>
                <div class="skillCatalogDesc">{{ s.description }}</div>
              </button>
            </div>

            <div v-if="selectedSkill" class="tabBody">
              <div class="skillTemplateHead">
                <div class="skillTemplateMeta">
                  <div class="skillTemplateTitle">{{ selectedSkill.name }}</div>
                  <div class="fieldTitle">{{ selectedSkill.description }}</div>
                </div>
                <div class="row compactRow wrapRow skillTemplateActions">
                  <button class="ghostBtn" :disabled="docsBusy" type="button" @click="resetSelectedSkillPayload">重置模板</button>
                  <button class="primaryBtn" :disabled="docsBusy" type="button" @click="runSelectedSkill">生成文件</button>
                </div>
              </div>

              <div class="skillTemplateEditor">
                <BuiltinSkillPayloadEditor v-model="selectedSkillPayload" />
              </div>

              <details class="skillAdvanced">
                <summary>高级模式（Markdown / JSON 预览）</summary>
                <div class="skillAdvancedBody">
                  <div v-if="selectedSkillPayloadMarkdown" class="skillAdvancedPanel">
                    <div class="subtle">Markdown</div>
                    <pre class="code">{{ selectedSkillPayloadMarkdown }}</pre>
                    <div class="md skillAdvancedMarkdown" v-html="renderMarkdown(selectedSkillPayloadMarkdown)" />
                  </div>
                  <div class="skillAdvancedPanel">
                    <div class="subtle">JSON</div>
                    <pre class="code">{{ selectedSkillPayloadJson }}</pre>
                  </div>
                </div>
              </details>

              <div v-if="skillDownloadById[selectedSkill.id]" class="row wrapRow">
                <a class="primaryBtn" :href="skillDownloadById[selectedSkill.id]!" target="_blank" rel="noreferrer">下载文件</a>
                <button class="ghostBtn" type="button" @click="copyToClipboard(skillDownloadById[selectedSkill.id]!)">复制链接</button>
              </div>
              <div v-if="skillDownloadById[selectedSkill.id]" class="subtle mono downloadUrl">
                {{ skillDownloadById[selectedSkill.id] }}
              </div>
              <div v-if="skillError" class="error">{{ skillError }}</div>
            </div>
            <div v-else class="subtle">正在加载内置技能模板…</div>
          </section>

          <section v-if="leftNavSection === 'skills'" ref="teamSkillsCard" class="card">
            <div class="cardHead">
              <div>
                <h3><span class="msIcon h3Icon" aria-hidden="true">group_work</span>团队技能</h3>
                <div class="subtle">注入到对话系统提示词</div>
              </div>
              <div class="cardHeadActions">
                <button class="ghostBtn" type="button" @click="scrollToBuiltinSkills">
                  <span class="msIcon btnIcon" aria-hidden="true">auto_awesome</span>
                  <span>内置模板</span>
                </button>
                <button class="ghostBtn" :disabled="teamDbExportBusy" type="button" @click="exportTeamDbMd">
                  <span class="msIcon btnIcon" aria-hidden="true">download</span>
                  <span>{{ teamDbExportBusy ? "导出中…" : "导出MD" }}</span>
                </button>
              </div>
            </div>

            <div v-if="teamSkills.length" class="tabs skillsTabs">
              <button
                v-for="s in teamSkills"
                :key="s.id"
                class="tab"
                :class="{ active: selectedTeamSkillId === s.id }"
                type="button"
                @click="selectTeamSkill(s)"
              >
                {{ s.name }}
              </button>
              <button v-if="canEditTeamSkills" class="tab" :class="{ active: selectedTeamSkillId === 'new' }" type="button" @click="newTeamSkill">
                + 新建
              </button>
            </div>
            <div v-else class="row">
              <div class="subtle">暂无团队技能。</div>
              <button v-if="canEditTeamSkills" class="ghostBtn" type="button" @click="newTeamSkill">+ 新建</button>
            </div>

            <div v-if="selectedTeamSkillId" class="tabBody">
              <div class="row">
                <input v-model="teamSkillForm.name" class="input" :disabled="!canEditTeamSkills" placeholder="技能名称" />
              </div>
              <div class="row">
                <input
                  v-model="teamSkillForm.description"
                  class="input"
                  :disabled="!canEditTeamSkills"
                  placeholder="一句话说明（可选）"
                />
              </div>
              <div class="row">
                <label class="chip" :class="{ disabled: !canEditTeamSkills }">
                  <input v-model="teamSkillForm.enabled" type="checkbox" :disabled="!canEditTeamSkills" />
                  <span>启用</span>
                </label>
              </div>
              <textarea
                v-model="teamSkillForm.content"
                class="textarea"
                :disabled="!canEditTeamSkills"
                placeholder="写下团队规范/技能提示词（Markdown）…"
              />
              <div class="row">
                <button class="primaryBtn" :disabled="teamSkillsBusy || !canEditTeamSkills" type="button" @click="saveTeamSkill">
                  保存
                </button>
                <button class="ghostBtn" :disabled="teamSkillsBusy || !canEditTeamSkills" type="button" @click="aiGenerateTeamSkill">
                  AI 生成
                </button>
                <button
                  v-if="selectedTeamSkillId !== 'new'"
                  class="ghostBtn"
                  :disabled="teamSkillsBusy || !canEditTeamSkills"
                  type="button"
                  @click="removeTeamSkill"
                >
                  删除
                </button>
                <button class="ghostBtn" :disabled="teamSkillsBusy" type="button" @click="refreshTeamSkills">刷新</button>
              </div>
              <div v-if="teamSkillsError" class="error">{{ teamSkillsError }}</div>
              <div v-if="teamDbExportError" class="error">{{ teamDbExportError }}</div>
              <div v-if="teamDbExport?.workspace_path" class="subtle mono pathLine">
                导出文件：{{ teamDbExport.workspace_path }}
              </div>
            </div>
          </section>

          <section v-if="leftNavSection === 'workspace' && workspacePanel === 'chatbi'" class="card">
            <div class="cardHead">
              <div>
                <h3><span class="msIcon h3Icon" aria-hidden="true">query_stats</span>智能问数（ChatBI）</h3>
                <div class="subtle">已在主面板打开（不再放在左侧卡片）</div>
              </div>
              <div class="cardHeadActions">
                <button class="ghostBtn" type="button" @click="reloadChatbi">
                  <span class="msIcon btnIcon" aria-hidden="true">refresh</span>
                  <span>刷新</span>
                </button>
              </div>
            </div>
            <div class="row" style="padding: 0 12px 12px;">
              <button class="ghostBtn" type="button" @click="showRight = true">
                <span class="msIcon btnIcon" aria-hidden="true">dock_to_right</span>
                <span>打开结果预览</span>
              </button>
            </div>
          </section>

          <section v-if="leftNavSection === 'workspace' && workspacePanel === 'browser'" class="card">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">travel_explore</span>浏览器</h3>
              <div class="subtle">AISTAFF_ENABLE_BROWSER=1 + Playwright</div>
            </div>
            <div class="row">
              <input v-model="browserUrl" class="input" placeholder="https://example.com" />
            </div>
            <div class="row">
              <button class="ghostBtn" :disabled="!sessionId" type="button" @click="startBrowser">启动</button>
              <button class="ghostBtn" :disabled="!sessionId || !browserUrl.trim()" type="button" @click="navBrowser">
                跳转
              </button>
              <button class="ghostBtn" :disabled="!sessionId" type="button" @click="shotBrowser">截图</button>
            </div>
            <div v-if="browserError" class="error">{{ browserError }}</div>
            <img v-if="browserImg" :src="browserImg" class="shot" />
          </section>
</template>

<script lang="ts">
import { defineComponent, nextTick, ref, type PropType } from "vue"
import BuiltinSkillPayloadEditor from "../BuiltinSkillPayloadEditor.vue"

export default defineComponent({
  name: "WorkspaceDomainPanel",
  components: {
    BuiltinSkillPayloadEditor,
  },
  props: {
    ctx: {
      type: Object as PropType<Record<string, any>>,
      required: true,
    },
  },
  setup(props) {
    const builtinSkillsCard = ref<HTMLElement | null>(null)
    const teamSkillsCard = ref<HTMLElement | null>(null)
    const chatbiReloadNonce = ref(0)

    function openChatbi() {
      const ctx = props.ctx as Record<string, any>
      try {
        if (ctx.leftNavSection && typeof ctx.leftNavSection === "object" && "value" in ctx.leftNavSection) {
          ctx.leftNavSection.value = "workspace"
        } else {
          ctx.leftNavSection = "workspace"
        }
        if (ctx.workspacePanel && typeof ctx.workspacePanel === "object" && "value" in ctx.workspacePanel) {
          ctx.workspacePanel.value = "chatbi"
        } else {
          ctx.workspacePanel = "chatbi"
        }
      } catch {
        // ignore
      }
    }

    function reloadChatbi() {
      chatbiReloadNonce.value += 1
    }

    async function scrollToTeamSkills() {
      await nextTick()
      teamSkillsCard.value?.scrollIntoView({ behavior: "smooth", block: "start" })
    }

    async function scrollToBuiltinSkills() {
      await nextTick()
      builtinSkillsCard.value?.scrollIntoView({ behavior: "smooth", block: "start" })
    }

    // Extend the shared ctx object, so template type-checking remains permissive (ctx is a Record<string, any>).
    const ctx = props.ctx as Record<string, any>
    ctx.builtinSkillsCard = builtinSkillsCard
    ctx.teamSkillsCard = teamSkillsCard
    ctx.openChatbi = openChatbi
    ctx.chatbiReloadNonce = chatbiReloadNonce
    ctx.reloadChatbi = reloadChatbi
    ctx.scrollToTeamSkills = scrollToTeamSkills
    ctx.scrollToBuiltinSkills = scrollToBuiltinSkills
    return ctx
  },
})
</script>
