<template>
          <div v-if="showProjectModal" class="modalOverlay" @click.self="showProjectModal = false">
        <div class="modal">
          <div class="modalHead">
            <div>
              <div class="modalTitle">项目/工作区管理</div>
              <div class="subtle">
                路径需存在，且位于服务端 AISTAFF_PROJECTS_ROOT 白名单内（默认等于 AISTAFF_WORKSPACE）
              </div>
            </div>
            <button class="ghostBtn" type="button" @click="showProjectModal = false">关闭</button>
          </div>

          <div class="modalSection">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">home_work</span>团队工作区</h3>
              <div class="subtle">默认对话/工具目录</div>
            </div>
            <div class="row">
              <input
                v-model="teamWorkspaceDraft"
                class="input"
                :disabled="!canEditTeamProjects"
                placeholder="留空则使用服务端 AISTAFF_WORKSPACE"
              />
            </div>
            <div class="row">
              <button class="primaryBtn" :disabled="teamSettingsBusy || !canEditTeamProjects" type="button" @click="saveTeamWorkspace">
                保存
              </button>
              <button
                class="ghostBtn"
                :disabled="teamSettingsBusy || !canEditTeamProjects || !teamWorkspacePath"
                type="button"
                @click="clearTeamWorkspace"
              >
                清空
              </button>
              <button class="ghostBtn" :disabled="teamSettingsBusy" type="button" @click="refreshTeamSettings">刷新</button>
            </div>
            <div class="subtle mono pathLine">
              当前：{{ teamWorkspacePath ?? "（未设置，回退到服务端 AISTAFF_WORKSPACE）" }}
            </div>
            <div v-if="teamSettingsError" class="error">{{ teamSettingsError }}</div>
          </div>

          <div class="divider"></div>

          <div v-if="teamProjects.length" class="tabs skillsTabs">
            <button
              v-for="p in teamProjects"
              :key="p.id"
              class="tab"
              :class="{ active: selectedTeamProjectId === p.id }"
              type="button"
              @click="selectTeamProject(p)"
            >
              {{ p.name }}
            </button>
            <button
              v-if="canEditTeamProjects"
              class="tab"
              :class="{ active: selectedTeamProjectId === 'new' }"
              type="button"
              @click="newTeamProject"
            >
              + 新建
            </button>
          </div>
          <div v-else class="row">
            <div class="subtle">暂无项目。</div>
            <button v-if="canEditTeamProjects" class="ghostBtn" type="button" @click="newTeamProject">+ 新建</button>
          </div>

          <div v-if="selectedTeamProjectId" class="tabBody">
            <div class="row">
              <input v-model="teamProjectForm.name" class="input" :disabled="!canEditTeamProjects" placeholder="项目名称" />
            </div>
            <div class="row">
              <input
                v-model="teamProjectForm.slug"
                class="input"
                :disabled="!canEditTeamProjects"
                placeholder="slug（可选，如 my-project）"
              />
            </div>
            <div class="row">
              <input
                v-model="teamProjectForm.path"
                class="input"
                :disabled="!canEditTeamProjects"
                placeholder="/Users/.../your-repo"
              />
            </div>
            <div class="row">
              <label class="chip" :class="{ disabled: !canEditTeamProjects }">
                <input v-model="teamProjectForm.enabled" type="checkbox" :disabled="!canEditTeamProjects" />
                <span>启用</span>
              </label>
            </div>
            <div class="row">
              <button class="primaryBtn" :disabled="teamProjectsBusy || !canEditTeamProjects" type="button" @click="saveTeamProject">
                保存
              </button>
              <button
                class="ghostBtn"
                :disabled="teamProjectsBusy || !canEditTeamProjects"
                type="button"
                @click="quickImportTeamProjects"
              >
                一键导入项目
              </button>
              <button
                v-if="selectedTeamProjectId !== 'new'"
                class="ghostBtn"
                :disabled="teamProjectsBusy || !canEditTeamProjects"
                type="button"
                @click="removeTeamProject"
              >
                删除
              </button>
              <button class="ghostBtn" :disabled="teamProjectsBusy" type="button" @click="refreshTeamProjects">刷新</button>
            </div>
            <div v-if="teamProjectsError" class="error">{{ teamProjectsError }}</div>
          </div>

          <div class="divider"></div>

          <div class="modalSection">
            <div class="cardHead">
              <h3><span class="msIcon h3Icon" aria-hidden="true">forum</span>飞书 Webhook</h3>
              <div class="subtle">事件回调 + 机器人回发（团队级）</div>
            </div>

            <div class="row compactRow wrapRow feishuModeRow">
              <label class="chip" :class="{ disabled: teamFeishuBusy }">
                <input v-model="feishuManageMode" type="radio" value="global" :disabled="teamFeishuBusy" />
                <span>整体管理</span>
              </label>
              <label class="chip" :class="{ disabled: teamFeishuBusy }">
                <input v-model="feishuManageMode" type="radio" value="single" :disabled="teamFeishuBusy" />
                <span>逐个配置</span>
              </label>
              <div class="subtle">
                共 {{ teamFeishuStats.total }} 个 · 已启用 {{ teamFeishuStats.enabled }} · 已停用 {{ teamFeishuStats.disabled }}
              </div>
            </div>

            <div v-if="feishuManageMode === 'global'" class="tabBody feishuGlobalPanel">
              <div class="row compactRow wrapRow">
                <button class="ghostBtn" :disabled="teamFeishuBusy || !canEditTeamFeishu" type="button" @click="setAllTeamFeishuEnabled(true)">
                  全部启用
                </button>
                <button class="ghostBtn" :disabled="teamFeishuBusy || !canEditTeamFeishu" type="button" @click="setAllTeamFeishuEnabled(false)">
                  全部停用
                </button>
                <button class="ghostBtn" :disabled="teamFeishuBusy || !canEditTeamFeishu" type="button" @click="importTeamFeishuPreset">
                  导入预配置
                </button>
                <button class="ghostBtn" :disabled="teamFeishuBusy" type="button" @click="refreshTeamFeishuWebhooks">刷新</button>
                <button
                  class="primaryBtn"
                  :disabled="teamFeishuBusy || !canEditTeamFeishu"
                  type="button"
                  @click="newTeamFeishuWebhook(); feishuManageMode = 'single'"
                >
                  + 新建机器人
                </button>
              </div>

              <div v-if="!teamFeishuWebhooks.length" class="subtle">暂无飞书 Webhook 配置。</div>
              <div v-else class="feishuGlobalList">
                <div
                  v-for="item in teamFeishuWebhooks"
                  :key="item.id"
                  class="feishuGlobalItem"
                  :class="{ active: selectedTeamFeishuId === item.id, disabled: !item.enabled }"
                >
                  <div class="feishuGlobalItemHead">
                    <div class="feishuGlobalName">{{ item.name }}</div>
                    <label class="chip" :class="{ disabled: teamFeishuBusy || !canEditTeamFeishu }">
                      <input
                        type="checkbox"
                        :checked="item.enabled"
                        :disabled="teamFeishuBusy || !canEditTeamFeishu"
                        @change="toggleTeamFeishuEnabled(item, ($event.target as HTMLInputElement).checked)"
                      />
                      <span>{{ item.enabled ? "启用中" : "已停用" }}</span>
                    </label>
                  </div>

                  <div class="subtle mono pathLine">回调：{{ item.callback_url }}</div>
                  <div class="subtle mono pathLine">Hook：{{ item.hook }}</div>

                  <div class="row compactRow wrapRow">
                    <button class="ghostBtn" type="button" @click="copyToClipboard(item.callback_url)">复制回调</button>
                    <button class="ghostBtn" type="button" @click="copyToClipboard(item.webhook_url)">复制机器人 URL</button>
                    <button
                      class="ghostBtn"
                      type="button"
                      @click="selectTeamFeishuWebhook(item); feishuManageMode = 'single'"
                    >
                      进入编辑
                    </button>
                  </div>
                </div>
              </div>
              <div v-if="teamFeishuError" class="error">{{ teamFeishuError }}</div>
            </div>

            <template v-else>
              <div v-if="teamFeishuWebhooks.length" class="tabs skillsTabs">
                <button
                  v-for="item in teamFeishuWebhooks"
                  :key="item.id"
                  class="tab"
                  :class="{ active: selectedTeamFeishuId === item.id }"
                  type="button"
                  @click="selectTeamFeishuWebhook(item)"
                >
                  {{ item.name }}
                </button>
                <button
                  v-if="canEditTeamFeishu"
                  class="tab"
                  :class="{ active: selectedTeamFeishuId === 'new' }"
                  type="button"
                  @click="newTeamFeishuWebhook"
                >
                  + 新建
                </button>
              </div>
              <div v-else class="row">
                <div class="subtle">暂无飞书 Webhook 配置。</div>
                <button v-if="canEditTeamFeishu" class="ghostBtn" type="button" @click="newTeamFeishuWebhook">+ 新建</button>
              </div>

              <div v-if="selectedTeamFeishuId" class="tabBody">
                <div class="row">
                  <input v-model="teamFeishuForm.name" class="input" :disabled="!canEditTeamFeishu" placeholder="配置名称" />
                </div>
                <div class="row">
                  <input
                    v-model="teamFeishuForm.webhook_url"
                    class="input"
                    :disabled="!canEditTeamFeishu"
                    placeholder="飞书机器人 webhook_url"
                  />
                </div>
                <div class="row">
                  <input
                    v-model="teamFeishuForm.verification_token"
                    class="input"
                    :disabled="!canEditTeamFeishu"
                    placeholder="事件订阅 verification_token（可选）"
                  />
                </div>
                <div class="row">
                  <label class="chip" :class="{ disabled: !canEditTeamFeishu }">
                    <input v-model="teamFeishuForm.enabled" type="checkbox" :disabled="!canEditTeamFeishu" />
                    <span>启用</span>
                  </label>
                </div>
                <div class="subtle mono pathLine" v-if="selectedTeamFeishu">
                  回调：{{ selectedTeamFeishu.callback_url }}
                </div>
                <div class="subtle mono pathLine" v-if="selectedTeamFeishu">
                  Hook：{{ selectedTeamFeishu.hook }}
                </div>
                <div class="row">
                  <button class="primaryBtn" :disabled="teamFeishuBusy || !canEditTeamFeishu" type="button" @click="saveTeamFeishuWebhook">
                    保存
                  </button>
                  <button
                    class="ghostBtn"
                    :disabled="teamFeishuBusy || !canEditTeamFeishu"
                    type="button"
                    @click="importTeamFeishuPreset"
                  >
                    导入预配置
                  </button>
                  <button
                    v-if="selectedTeamFeishuId !== 'new'"
                    class="ghostBtn"
                    :disabled="teamFeishuBusy || !canEditTeamFeishu"
                    type="button"
                    @click="removeTeamFeishuWebhook"
                  >
                    删除
                  </button>
                  <button class="ghostBtn" :disabled="teamFeishuBusy" type="button" @click="refreshTeamFeishuWebhooks">刷新</button>
                </div>
                <div v-if="teamFeishuError" class="error">{{ teamFeishuError }}</div>
              </div>
            </template>
          </div>
        </div>
      </div>
      <div v-if="showTopMenu" class="modalOverlay" @click.self="showTopMenu = false">
        <div class="modal topMenuModal">
          <div class="modalHead">
            <div>
              <div class="modalTitle">菜单</div>
              <div class="subtle">{{ me.user.name }} · {{ me.active_team.name }}（{{ me.active_team.role }}）</div>
            </div>
            <button class="ghostBtn" type="button" @click="showTopMenu = false">关闭</button>
          </div>

          <div class="modalSection">
            <div class="fieldTitle">工作模式</div>

            <label class="select wide">
              <span class="label">档案</span>
              <select v-model="selectedAgentProfileId" @change="applyAgentProfile(selectedAgentProfileId)">
                <option value="custom">自定义（保持当前）</option>
                <option v-for="p in agentProfiles" :key="p.id" :value="p.id">{{ p.name }} · {{ p.description }}</option>
              </select>
            </label>

	            <label v-if="me.teams.length > 1" class="select wide">
	              <span class="label">团队</span>
	              <select v-model.number="activeTeamId" @change="onSwitchTeam">
	                <option v-for="t in me.teams" :key="t.id" :value="t.id">{{ t.name }}（{{ t.role }}）</option>
	              </select>
	            </label>

	            <div class="row compactRow wrapRow">
	              <button class="ghostBtn iconBtn" type="button" @click="openAdminTeamsManager">
	                <span class="msIcon btnIcon" aria-hidden="true">group</span>
	                <span>团队管理</span>
	              </button>
	              <div v-if="me.teams.length <= 1" class="subtle">当前仅 1 个团队；可在此新建更多团队。</div>
	            </div>

	            <label class="select wide">
	              <span class="label">提供商</span>
	              <select v-model="provider">
	                <option v-if="availableProviders?.includes('openai')" value="openai">OpenAI</option>
	                <option v-if="availableProviders?.includes('pi')" value="pi">Pi（pi-mono）</option>
	                <option v-if="availableProviders?.includes('codex')" value="codex">Codex CLI</option>
                <option v-if="availableProviders?.includes('opencode')" value="opencode">OpenCode</option>
                <option v-if="availableProviders?.includes('nanobot')" value="nanobot">NanoBot</option>
                <option v-if="availableProviders?.includes('mock')" value="mock">模拟</option>
              </select>
            </label>

            <label class="select wide">
              <span class="label">角色</span>
              <select v-model="role">
                <option value="general">通用</option>
                <option value="engineer">工程</option>
              </select>
            </label>

            <label class="select wide">
              <span class="label">安全</span>
              <select v-model="securityPreset" :disabled="!canEditTeamSkills">
                <option value="safe">safe（仅读）</option>
                <option value="standard">standard（可写）</option>
                <option value="power">power（全能力）</option>
                <option value="custom">custom（手动）</option>
              </select>
            </label>

            <label class="select wide">
              <span class="label">风格</span>
              <select v-model="vibe">
                <option value="pro">Notion（推荐）</option>
                <option value="toc">Glass（灵动）</option>
                <option value="notebook">NotebookLM（分栏）</option>
              </select>
            </label>

            <label class="select wide">
              <span class="label">密度</span>
              <select v-model="densityMode">
                <option value="auto">auto（推荐）</option>
                <option value="compact">compact（紧凑）</option>
                <option value="normal">normal（标准）</option>
                <option value="comfortable">comfortable（舒展）</option>
              </select>
            </label>
            <div class="subtle">当前密度：{{ densityLabel }}</div>

            <div class="row">
              <button class="ghostBtn iconBtn" type="button" @click="toggleTheme">
                <span class="msIcon btnIcon" aria-hidden="true">{{ theme === "dark" ? "light_mode" : "dark_mode" }}</span>
                <span>{{ theme === "dark" ? "切换到浅色" : "切换到深色" }}</span>
              </button>
              <button class="ghostBtn iconBtn" type="button" @click="logout">
                <span class="msIcon btnIcon" aria-hidden="true">logout</span>
                <span>退出</span>
              </button>
		            </div>
	          </div>
	        </div>
	      </div>

	      <div v-if="showTeamCenter && me" class="modalOverlay" @click.self="closeTeamCenter">
	        <div class="modal">
	          <div class="modalHead">
	            <div>
	              <div class="modalTitle">团队管理</div>
	              <div class="subtle">团队切换 · 状态/人数/需求统计</div>
	            </div>
	            <div class="row compactRow wrapRow">
	              <button class="ghostBtn" :disabled="teamOverviewBusy" type="button" @click="refreshTeamOverviews">刷新</button>
	              <button class="ghostBtn" type="button" @click="closeTeamCenter">关闭</button>
	            </div>
	          </div>

	          <div class="modalSection">
	            <div class="row compactRow wrapRow">
	              <span class="metaPill">当前：{{ me.active_team.name }}（{{ me.active_team.role }}）</span>
	              <span class="metaPill">团队数 {{ teamOverviews.length }}</span>
	            </div>

	            <div v-if="teamOverviewBusy" class="subtle">正在加载团队概览…</div>
	            <div v-else-if="!teamOverviews.length" class="subtle">暂无团队。</div>
	            <div v-else class="historyList workspaceList">
	              <div v-for="t in teamOverviews" :key="t.id" class="historyItem workspaceListItem">
	                <div class="historyItemMain workspaceListMain">
	                  <div class="historyTitle">{{ t.name }}</div>
	                  <div class="historyMetaRow">
	                    <span class="metaPill">ID: {{ t.id }}</span>
	                    <span class="metaPill">角色：{{ t.role }}</span>
	                    <span class="metaPill">{{ me.active_team.id === t.id ? "当前" : "可切换" }}</span>
	                    <span>成员：{{ t.members }}</span>
	                    <span>项目：{{ t.projects }}</span>
	                    <span>技能：{{ t.skills }}</span>
	                  </div>
	                  <div class="historyMetaRow">
	                    <span>
	                      需求：新交付 {{ t.requirements_incoming }} · 待处理 {{ t.requirements_todo }} · 处理中 {{ t.requirements_in_progress }} ·
	                      已完成 {{ t.requirements_done }} · 阻塞 {{ t.requirements_blocked }}
	                    </span>
	                  </div>
	                  <div class="historyMetaRow">
	                    <span>总需求：{{ t.requirements_total }}</span>
	                    <span v-if="t.last_activity_at">最近活跃：{{ formatIsoTime(t.last_activity_at) }}</span>
	                    <span v-else>最近活跃：—</span>
	                    <span>工作区：{{ t.workspace_path ? "自定义" : "默认" }}</span>
	                  </div>
	                </div>
	                <div class="historyActions">
	                  <button class="ghostBtn" :disabled="me.active_team.id === t.id" type="button" @click="switchTeamFromCenter(t.id)">
	                    {{ me.active_team.id === t.id ? "当前" : "切换" }}
	                  </button>
	                </div>
	              </div>
	            </div>

		            <div v-if="teamOverviewError" class="error">{{ teamOverviewError }}</div>
		          </div>

		          <div class="divider"></div>

		          <div class="modalSection">
		            <div class="cardHead">
		              <h3><span class="msIcon h3Icon" aria-hidden="true">person_add</span>邀请码注册</h3>
		              <button class="ghostBtn" :disabled="teamInvitesBusy || !canEditTeamSkills" type="button" @click="refreshTeamInvites">
		                刷新
		              </button>
		            </div>

		            <div v-if="!canEditTeamSkills" class="subtle">需要 owner/admin 权限才能生成邀请码。</div>
		            <template v-else>
		              <div class="row compactRow wrapRow">
		                <input v-model="inviteEmailDraft" class="input" placeholder="绑定邮箱（可选）" />
		                <label class="select">
		                  <span class="label">角色</span>
		                  <select v-model="inviteRoleDraft" :disabled="teamInvitesBusy">
		                    <option value="member">member</option>
		                    <option value="admin" :disabled="me.active_team.role !== 'owner'">admin</option>
		                  </select>
		                </label>
		                <input
		                  v-model.number="inviteExpiresDaysDraft"
		                  class="input"
		                  type="number"
		                  min="1"
		                  max="365"
		                  placeholder="有效期(天)"
		                />
		                <button class="primaryBtn" :disabled="teamInvitesBusy" type="button" @click="createTeamInvite">
		                  生成邀请码
		                </button>
		              </div>

		              <div v-if="teamInvitesBusy" class="subtle">正在加载邀请码…</div>
		              <div v-else-if="!teamInvites.length" class="subtle">暂无邀请码。</div>
		              <div v-else class="historyList workspaceList">
		                <div v-for="inv in teamInvites" :key="inv.id" class="historyItem workspaceListItem">
		                  <div class="historyItemMain workspaceListMain">
		                    <div class="historyTitle">邀请码 #{{ inv.id }}</div>
		                    <div class="historyMetaRow">
		                      <span class="metaPill">角色：{{ inv.role }}</span>
		                      <span v-if="inv.email" class="metaPill">邮箱：{{ inv.email }}</span>
		                      <span class="metaPill">{{ inv.used_at ? "已使用" : "未使用" }}</span>
		                    </div>
		                    <div class="subtle mono pathLine">Token：{{ inv.token }}</div>
		                    <div class="historyMetaRow">
		                      <span>创建：{{ formatIsoTime(inv.created_at) }}</span>
		                      <span>过期：{{ formatIsoTime(inv.expires_at) }}</span>
		                    </div>
		                  </div>
		                  <div class="historyActions">
		                    <button class="ghostBtn" type="button" @click="copyToClipboard(inv.token)">复制</button>
		                    <button class="ghostBtn" :disabled="teamInvitesBusy" type="button" @click="deleteTeamInvite(inv.id)">
		                      删除
		                    </button>
		                  </div>
		                </div>
		              </div>

		              <div v-if="teamInvitesError" class="error">{{ teamInvitesError }}</div>
		            </template>
		          </div>
		        </div>
		      </div>

	      <div v-if="showAdminTeamsModal" class="modalOverlay" @click.self="closeAdminTeamsManager">
	        <div class="modal">
	          <div class="modalHead">
	            <div>
	              <div class="modalTitle">团队管理</div>
	              <div class="subtle">仅超级管理员可创建/重命名团队</div>
	            </div>
	            <button class="ghostBtn" type="button" @click="closeAdminTeamsManager">关闭</button>
	          </div>

	          <div class="modalSection">
	            <div class="cardHead">
	              <h3><span class="msIcon h3Icon" aria-hidden="true">group</span>团队列表</h3>
	              <button class="ghostBtn" :disabled="adminTeamsBusy" type="button" @click="refreshAdminTeams">刷新</button>
	            </div>

	            <div v-if="adminTeamsBusy" class="subtle">正在加载团队…</div>
	            <div v-else-if="!adminTeams.length" class="subtle">暂无团队。</div>
	            <div v-else class="historyList workspaceList">
	              <div v-for="t in adminTeams" :key="t.id" class="historyItem workspaceListItem">
	                <div class="historyItemMain workspaceListMain">
	                  <div class="historyTitle">{{ t.name }}</div>
	                  <div class="historyMetaRow">
	                    <span class="metaPill">ID: {{ t.id }}</span>
	                    <span>成员：{{ t.members }}</span>
	                    <span>{{ formatIsoTime(t.created_at) }}</span>
	                  </div>
	                </div>
	                <div class="historyActions">
	                  <button class="ghostBtn" :disabled="me.active_team.id === t.id" type="button" @click="switchToTeam(t.id)">
	                    {{ me.active_team.id === t.id ? "当前" : "切换" }}
	                  </button>
	                </div>

	                <div class="row compactRow wrapRow">
	                  <input v-model="adminTeamNameDraftById[t.id]" class="input" placeholder="重命名团队…" />
	                  <button
	                    class="ghostBtn"
	                    :disabled="adminTeamsBusy || !(adminTeamNameDraftById[t.id] || '').trim()"
	                    type="button"
	                    @click="renameAdminTeam(t.id)"
	                  >
	                    保存名称
	                  </button>
	                </div>
	              </div>
	            </div>

	            <div v-if="adminTeamsError" class="error">{{ adminTeamsError }}</div>
	          </div>

	          <div class="divider"></div>

	          <div class="modalSection">
	            <div class="cardHead">
	              <h3><span class="msIcon h3Icon" aria-hidden="true">add</span>新建团队</h3>
	            </div>
	            <div class="row compactRow wrapRow">
	              <input v-model="newAdminTeamName" class="input" placeholder="团队名称（如：chenhao）" />
	              <button class="primaryBtn" :disabled="adminTeamsBusy || !newAdminTeamName.trim()" type="button" @click="createAdminTeam">
	                创建
	              </button>
	            </div>
	          </div>
	        </div>
	      </div>
	</template>

		<script lang="ts">
		import axios from "axios"
		import { defineComponent, ref, watch, type PropType } from "vue"

	export default defineComponent({
	  name: "TeamManagementDomain",
	  props: {
	    ctx: {
      type: Object as PropType<Record<string, any>>,
	      required: true,
	    },
		  },
			  setup(props) {
			    type TeamOverview = {
			      id: number
			      name: string
			      role: string
			      created_at: string
		      members: number
		      projects: number
		      skills: number
		      requirements_total: number
		      requirements_incoming: number
		      requirements_todo: number
		      requirements_in_progress: number
		      requirements_done: number
		      requirements_blocked: number
			      workspace_path: string | null
			      last_activity_at: string | null
			    }
			    type TeamInvite = {
			      id: number
			      team_id: number
			      email: string | null
			      role: "admin" | "member"
			      token: string
			      created_by: number | null
			      created_at: string
			      expires_at: string
			      used_at: string | null
			      used_by: number | null
			    }
			    type AdminTeam = { id: number; name: string; created_at: string; members: number }

			    const showAdminTeamsModal = ref(false)
			    const adminTeamsBusy = ref(false)
			    const adminTeamsError = ref<string | null>(null)
		    const adminTeams = ref<AdminTeam[]>([])
		    const newAdminTeamName = ref("")
		    const adminTeamNameDraftById = ref<Record<number, string>>({})

			    const teamOverviewBusy = ref(false)
			    const teamOverviewError = ref<string | null>(null)
			    const teamOverviews = ref<TeamOverview[]>([])

			    const teamInvitesBusy = ref(false)
			    const teamInvitesError = ref<string | null>(null)
			    const teamInvites = ref<TeamInvite[]>([])
			    const inviteEmailDraft = ref("")
			    const inviteRoleDraft = ref<"member" | "admin">("member")
			    const inviteExpiresDaysDraft = ref<number>(7)

			    async function refreshMe() {
			      try {
			        const res = await axios.get("/api/me")
			        // ctx.me is a Ref in App.vue
		        props.ctx.me.value = res.data
		        props.ctx.activeTeamId.value = res.data?.active_team?.id ?? props.ctx.activeTeamId.value
		      } catch {
		        // ignore (auth flow will handle)
			      }
			    }

			    function canManageInvites(): boolean {
			      try {
			        return Boolean(props.ctx?.canEditTeamSkills?.value)
			      } catch {
			        return false
			      }
			    }

			    async function refreshTeamInvites() {
			      if (!canManageInvites()) return
			      teamInvitesBusy.value = true
			      teamInvitesError.value = null
			      try {
			        const res = await axios.get("/api/team/invites")
			        teamInvites.value = (res.data || []) as TeamInvite[]
			      } catch (e: any) {
			        teamInvitesError.value = typeof props.ctx.formatAxiosError === "function" ? props.ctx.formatAxiosError(e) : String(e)
			        teamInvites.value = []
			      } finally {
			        teamInvitesBusy.value = false
			      }
			    }

			    async function createTeamInvite() {
			      if (!canManageInvites()) return
			      const email = String(inviteEmailDraft.value || "").trim().toLowerCase()
			      const role = inviteRoleDraft.value === "admin" ? "admin" : "member"
			      const expires_days = Math.min(365, Math.max(1, Math.floor(Number(inviteExpiresDaysDraft.value || 7))))

			      teamInvitesBusy.value = true
			      teamInvitesError.value = null
			      try {
			        const res = await axios.post("/api/team/invites", {
			          email: email ? email : null,
			          role,
			          expires_days,
			        })
			        const invite = (res.data || null) as TeamInvite | null
			        if (invite) {
			          if (typeof props.ctx.copyToClipboard === "function") props.ctx.copyToClipboard(invite.token)
			          if (typeof props.ctx.showToast === "function") props.ctx.showToast("已生成邀请码（已复制）")
			        } else {
			          if (typeof props.ctx.showToast === "function") props.ctx.showToast("已生成邀请码")
			        }
			        inviteEmailDraft.value = ""
			        inviteRoleDraft.value = "member"
			        inviteExpiresDaysDraft.value = 7
			        await refreshTeamInvites()
			      } catch (e: any) {
			        teamInvitesError.value = typeof props.ctx.formatAxiosError === "function" ? props.ctx.formatAxiosError(e) : String(e)
			      } finally {
			        teamInvitesBusy.value = false
			      }
			    }

			    async function deleteTeamInvite(inviteId: number) {
			      if (!canManageInvites()) return
			      teamInvitesBusy.value = true
			      teamInvitesError.value = null
			      try {
			        await axios.delete(`/api/team/invites/${inviteId}`)
			        await refreshTeamInvites()
			        if (typeof props.ctx.showToast === "function") props.ctx.showToast("已删除邀请码")
			      } catch (e: any) {
			        teamInvitesError.value = typeof props.ctx.formatAxiosError === "function" ? props.ctx.formatAxiosError(e) : String(e)
			      } finally {
			        teamInvitesBusy.value = false
			      }
			    }

			    async function refreshTeamOverviews() {
			      teamOverviewBusy.value = true
			      teamOverviewError.value = null
			      try {
		        const res = await axios.get("/api/team/teams")
		        teamOverviews.value = (res.data || []) as TeamOverview[]
		      } catch (e: any) {
		        teamOverviewError.value = typeof props.ctx.formatAxiosError === "function" ? props.ctx.formatAxiosError(e) : String(e)
		        teamOverviews.value = []
		      } finally {
		        teamOverviewBusy.value = false
		      }
		    }

			    function closeTeamCenter() {
			      props.ctx.showTeamCenter.value = false
			      teamOverviewError.value = null
			      teamInvitesError.value = null
			    }

		    async function switchTeamFromCenter(teamId: number) {
		      const me = props.ctx.me?.value
		      const beforeTeamId = Number(me?.active_team?.id ?? 0) || undefined
		      props.ctx.activeTeamId.value = teamId
		      await props.ctx.onSwitchTeam()
		      const afterTeamId = Number(props.ctx.me?.value?.active_team?.id ?? 0) || undefined
		      if (afterTeamId && afterTeamId === teamId) {
		        closeTeamCenter()
		        return
		      }
		      if (beforeTeamId) props.ctx.activeTeamId.value = beforeTeamId
		    }

		    async function refreshAdminTeams() {
		      adminTeamsBusy.value = true
		      adminTeamsError.value = null
		      try {
		        const res = await axios.get("/api/admin/teams")
	        const list = (res.data || []) as AdminTeam[]
	        adminTeams.value = list
	        const draft: Record<number, string> = {}
	        for (const t of list) draft[t.id] = t.name
	        adminTeamNameDraftById.value = draft
	      } catch (e: any) {
	        adminTeamsError.value = typeof props.ctx.formatAxiosError === "function" ? props.ctx.formatAxiosError(e) : String(e)
	        adminTeams.value = []
	      } finally {
	        adminTeamsBusy.value = false
	      }
	    }

	    async function openAdminTeamsManager() {
	      showAdminTeamsModal.value = true
	      props.ctx.showTopMenu.value = false
	      await refreshAdminTeams()
	    }

	    function closeAdminTeamsManager() {
	      showAdminTeamsModal.value = false
	      adminTeamsError.value = null
	    }

	    async function createAdminTeam() {
	      const name = newAdminTeamName.value.trim()
	      if (!name) return
	      adminTeamsBusy.value = true
	      adminTeamsError.value = null
	      try {
	        await axios.post("/api/admin/teams", { name })
	        newAdminTeamName.value = ""
	        await Promise.all([refreshAdminTeams(), refreshMe()])
	        if (typeof props.ctx.showToast === "function") props.ctx.showToast(`已创建团队：${name}`)
	      } catch (e: any) {
	        adminTeamsError.value = typeof props.ctx.formatAxiosError === "function" ? props.ctx.formatAxiosError(e) : String(e)
	      } finally {
	        adminTeamsBusy.value = false
	      }
	    }

	    async function renameAdminTeam(teamId: number) {
	      const name = String(adminTeamNameDraftById.value[teamId] || "").trim()
	      if (!name) return
	      adminTeamsBusy.value = true
	      adminTeamsError.value = null
	      try {
	        await axios.put(`/api/admin/teams/${teamId}`, { name })
	        await Promise.all([refreshAdminTeams(), refreshMe()])
	        if (typeof props.ctx.showToast === "function") props.ctx.showToast(`已更新团队名称：${name}`)
	      } catch (e: any) {
	        adminTeamsError.value = typeof props.ctx.formatAxiosError === "function" ? props.ctx.formatAxiosError(e) : String(e)
	      } finally {
	        adminTeamsBusy.value = false
	      }
	    }

		    async function switchToTeam(teamId: number) {
		      try {
		        props.ctx.activeTeamId.value = teamId
		        await props.ctx.onSwitchTeam()
		        closeAdminTeamsManager()
		      } catch {
		        // ignore (onSwitchTeam handles errors)
		      }
		    }

			    watch(
			      () => Boolean(props.ctx.showTeamCenter?.value),
			      (open) => {
			        if (open) {
			          refreshTeamOverviews()
			          refreshTeamInvites()
			        }
			      },
			    )

		    const ctx = props.ctx as any
		    return {
		      ...ctx,
		      teamOverviewBusy,
			      teamOverviewError,
			      teamOverviews,
			      teamInvitesBusy,
			      teamInvitesError,
			      teamInvites,
			      inviteEmailDraft,
			      inviteRoleDraft,
			      inviteExpiresDaysDraft,
			      refreshTeamOverviews,
			      refreshTeamInvites,
			      createTeamInvite,
			      deleteTeamInvite,
			      closeTeamCenter,
			      switchTeamFromCenter,
			      showAdminTeamsModal,
		      adminTeamsBusy,
		      adminTeamsError,
		      adminTeams,
	      newAdminTeamName,
	      adminTeamNameDraftById,
	      refreshAdminTeams,
	      openAdminTeamsManager,
	      closeAdminTeamsManager,
	      createAdminTeam,
	      renameAdminTeam,
	      switchToTeam,
	    } as any
	  },
	})
	</script>
