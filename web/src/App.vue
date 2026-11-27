<template>
  <div class="app-shell" :class="{ 'nav-collapsed': navCollapsed, 'chat-shell': route.name === 'requirement-intake' || route.name === 'requirement-conversation' || tab === 'assistant' }">
    <AppHeader ref="header" :items="visibleTabs" :active="tab" :collapsed="navCollapsed" :user="user" :badges="navBadges"
      @navigate="switchTab" @notification="onNotification" @login="authDialog = true" @toggle="toggleNavigation" @user-command="onUserCommand" @command="paletteOpen = true" />

    <main class="main">
      <Transition name="view" mode="out-in">
        <div :key="viewKey" class="view-root" :class="{ 'view-chat': isChatView }">
      <!-- ============ 需求详情页 ============ -->
      <IntakePage v-if="route.name === 'requirement-intake' || tab === 'assistant'" />
      <ConversationPage v-else-if="route.name === 'requirement-conversation'" :key="String(route.params.number)" :number="Number(route.params.number)" />
      <NotificationConfirmPage v-else-if="route.name === 'notification-confirm'" />
      <NotificationAdminPage v-else-if="tab === 'notifications' && isManager" />
      <section v-else-if="detailRouteNumber">
        <div v-if="detailLoading" class="panel empty">正在加载 REQ-{{ detailRouteNumber }}…</div>
        <RequirementDetail
          v-else-if="detailTarget"
          :requirement="detailTarget"
          :history="detailHistory"
          :manager="isManager"
          :can-edit="detailCanEdit"
          :has-receipt="!!receipts.tokenFor(detailTarget.id)"
          :edit-reason="detailEditReason"
          :can-supplement="detailCanSupplement"
          :supplements="detailSupplements"
          :supplements-error="supplementsError"
          :can-follow="canFollow"
          :can-edit-summary="canEditSummary"
          :user-role="user?.role || 'viewer'"
          @back="closeDetail"
          @copy-link="copyRequirementLink(detailTarget)"
          @copy-management="saveManagementLink(detailTarget)"
          @continue-a-i="continueWithAI(detailTarget)"
          @supplement="openSupplement(detailTarget)"
          @follow="followDetail"
          @edit="openEdit(detailTarget)"
          @status="openStatusChange(detailTarget)"
          @review="openReview(detailTarget)"
          @download="downloadAttachment(detailTarget, $event)"
          @refresh="refreshDetail"
        />
        <div v-else class="panel empty">需求不存在或你没有查看权限。</div>
      </section>

      <PublicRequirementsPage v-else-if="tab === 'public'" :stats="stats" :filters="filters" :status-options="statusOptions"
        v-model:sort-by="sortBy" :items="sortedRequirements" :manager="isManager" :user="user" :loading="listLoading" :error="listError"
        @reload="loadRequirements" @submit="switchTab('submit')" @discuss="router.push({ name: 'requirement-intake' })" @open="openDetail" @action="onRowAction" />

      <!-- ============ 管理总览 ============ -->
      <DashboardPage v-else-if="tab === 'dashboard' && dashboard" :data="dashboard" :loading="dashboardLoading" :manager="isManager"
        @reload="loadDashboard" @navigate="switchTab" @open-detail="openDetail" />
      <section v-else-if="tab === 'dashboard'" class="sk-page" aria-busy="true" aria-label="正在加载看板">
        <div class="sk-page-head">
          <span class="sk sk-icon"></span>
          <div><span class="sk sk-title"></span><span class="sk sk-sub"></span></div>
        </div>
        <div class="sk-grid">
          <span v-for="n in 4" :key="n" class="sk sk-card"></span>
        </div>
        <div class="sk-grid-2">
          <span class="sk sk-block"></span>
          <span class="sk sk-block"></span>
        </div>
      </section>

      <!-- ============ 提交需求 ============ -->
      <section v-else-if="tab === 'submit'" class="submission-page">
        <div class="page-head">
          <div class="page-head-left">
            <div class="page-head-icon"><el-icon :size="23"><EditPen /></el-icon></div>
            <div>
              <h1>提交需求</h1>
              <p class="sub">问题、建议、想要的功能，都可以告诉我们。</p>
            </div>
          </div>
          <button class="primary-action" type="button" @click="router.push({ name: 'requirement-intake' })">
            <el-icon :size="15"><MagicStick /></el-icon>与 AI 一起整理
          </button>
        </div>

        <SubmissionResult v-if="submittedRequirement" :requirement="submittedRequirement" :has-receipt="!!receipts.tokenFor(submittedRequirement.id)" @open="openAnalyzedRequirement" @save="saveManagementLink(submittedRequirement)" @continue-a-i="continueWithAI(submittedRequirement)" />

        <div class="submit-layout">
          <el-form class="panel submit-form" label-position="top" @submit.prevent="submitRequirement" @paste="handlePaste">
            <section class="form-section">
              <h2 class="form-section-title">需求类型</h2>
              <div class="type-cards" role="radiogroup" aria-label="需求类型">
                <button v-for="option in submitTypes" :key="option.value" type="button" role="radio"
                  :aria-checked="requirementForm.type === option.value" class="type-card"
                  :class="[option.value, { active: requirementForm.type === option.value }]"
                  @click="requirementForm.type = option.value">
                  <span class="tc-ico"><el-icon :size="19"><component :is="option.icon" /></el-icon></span>
                  <span class="tc-copy"><strong>{{ option.label }}</strong><small>{{ option.hint }}</small></span>
                  <span class="tc-check" aria-hidden="true"><el-icon :size="12"><Check /></el-icon></span>
                </button>
              </div>
            </section>

            <section class="form-section">
              <h2 class="form-section-title">需求描述</h2>
              <el-form-item label="标题" required>
                <el-input v-model="requirementForm.title" maxlength="160" show-word-limit size="large" placeholder="一句话说清你希望改变什么（至少 4 字）" />
              </el-form-item>
              <el-form-item label="详细描述" required>
                <el-input v-model="requirementForm.description" type="textarea" :autosize="{ minRows: 5, maxRows: 14 }" maxlength="8000" show-word-limit placeholder="在什么场景下遇到了什么问题？你期待怎样的结果？补充截图、设备或版本会更容易定位。" />
              </el-form-item>
            </section>

            <details class="optional-fields">
              <summary><span class="opt-ico"><el-icon :size="14"><DocumentAdd /></el-icon></span>补充细节<span class="opt-tag">选填</span></summary>
              <div class="optional-body">
                <el-form-item label="期望结果"><el-input v-model="requirementForm.expected_behavior" type="textarea" :rows="2" maxlength="3000" placeholder="希望如何改进" /></el-form-item>
                <el-form-item v-if="requirementForm.type === 'bug'" label="复现步骤"><el-input v-model="requirementForm.steps_to_reproduce" type="textarea" :rows="3" maxlength="4000" placeholder="1. 打开… 2. 点击… 3. 出现…" /></el-form-item>
                <el-form-item label="当前情况"><el-input v-model="requirementForm.current_behavior" type="textarea" :rows="2" maxlength="3000" /></el-form-item>
                <div class="form-grid"><el-form-item label="影响程度"><el-select v-model="requirementForm.severity"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item><el-form-item label="行影集版本"><el-input v-model="requirementForm.product_version" maxlength="50" placeholder="例如 0.14.1" /></el-form-item></div>
                <el-form-item v-if="!user" label="昵称"><el-input v-model="requirementForm.submitter_name" maxlength="50" placeholder="如何称呼你" /></el-form-item>
              </div>
            </details>

            <details class="optional-fields" :open="pendingFiles.length > 0">
              <summary><span class="opt-ico"><el-icon :size="14"><Picture /></el-icon></span>截图与日志<span class="opt-tag">仅本人和管理员可见</span><span v-if="pendingFiles.length" class="opt-count">{{ pendingFiles.length }} 个附件</span></summary>
              <div class="optional-body">
                <el-form-item label="截图或附件">
                  <label class="dropzone">
                    <input ref="fileInput" class="native-file" type="file" multiple accept=".png,.jpg,.jpeg,.webp,.txt,.log,.json,.pdf" @change="selectFiles" />
                    <el-icon :size="20"><UploadFilled /></el-icon>
                    <span>拖入或点击选择文件，也支持直接粘贴截图</span>
                    <small>最多 5 个，每个 5MB · PNG / JPG / WEBP / TXT / LOG / JSON / PDF</small>
                  </label>
                  <div v-if="pendingFiles.length" class="file-list">
                    <div v-for="(file, index) in pendingFiles" :key="`${file.name}-${index}`" class="file-row">
                      <el-icon :size="14"><Document /></el-icon>
                      <span>{{ file.name }}</span>
                      <small>{{ formatBytes(file.size) }}</small>
                      <el-button link type="danger" @click="pendingFiles.splice(index, 1)">移除</el-button>
                    </div>
                  </div>
                </el-form-item>
                <el-form-item label="错误日志"><el-input v-model="requirementForm.log_text" type="textarea" :rows="3" maxlength="20000" show-word-limit placeholder="粘贴前请移除密码与密钥" /></el-form-item>
              </div>
            </details>

            <section class="form-section">
              <h2 class="form-section-title">跟进方式</h2>
              <RequirementContact v-model:email="requirementForm.notification_email" v-model:opt-in="requirementForm.notification_opt_in" />
              <el-form-item v-if="user" label="公开范围">
                <el-radio-group v-model="requirementForm.visibility">
                  <el-radio-button value="public">公开</el-radio-button>
                  <el-radio-button value="private">仅本人和管理员</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <p v-else class="submission-privacy"><el-icon :size="13"><Lock /></el-icon>需求公开展示，邮箱和附件不会公开。</p>
            </section>

            <div class="submit-actions">
              <el-button type="primary" size="large" :icon="Promotion" :loading="busy" native-type="submit">提交需求</el-button>
              <el-button size="large" @click="saveDraft">保存草稿</el-button>
              <span class="submit-hint">提交后仍可补充信息</span>
            </div>
          </el-form>

          <aside class="submission-aside">
            <div class="side-card aside-ai">
              <div class="aside-ai-orb"><el-icon :size="19"><MagicStick /></el-icon></div>
              <h3>不确定怎么写？</h3>
              <p>描述你的使用场景，AI 会追问细节，并实时整理成一份可编辑的需求单。</p>
              <button class="primary-action" type="button" style="width:100%" @click="router.push({ name: 'requirement-intake' })">让 AI 帮我整理</button>
            </div>
            <div class="side-card">
              <h3>写成这样更容易被采纳</h3>
              <ul class="aside-tips">
                <li><span>场景</span>在做什么时遇到了这个问题</li>
                <li><span>结果</span>期待看到什么变化</li>
                <li><span>证据</span>截图、日志、复现步骤</li>
              </ul>
            </div>
            <div class="side-card">
              <h3>接下来会发生什么</h3>
              <ol class="mini-trail">
                <li><i></i><div><strong>提交</strong><small>需求进入公开列表</small></div></li>
                <li><i></i><div><strong>AI 整理</strong><small>后台分析，无需等待</small></div></li>
                <li><i></i><div><strong>维护者评估</strong><small>可能追问细节</small></div></li>
                <li><i></i><div><strong>实现与发布</strong><small>订阅后可收到通知</small></div></li>
              </ol>
            </div>
          </aside>
        </div>
      </section>

      <!-- ============ 我的需求 ============ -->
      <MyRequirementsPage v-else-if="tab === 'mine'" :items="myRequirements" :manager="isManager" :user="user"
        @login="authDialog = true" @submit="switchTab('submit')" @open="openDetail" @action="onRowAction" />

      <!-- ============ 版本计划 ============ -->
      <VersionPlanPage v-else-if="tab === 'versions'" :batches="batches" :candidates="candidates" :manager="isManager"
        :candidate-selection="candidateSelection" :delivery-statuses="deliveryStatuses" :allowed-statuses="allowedBatchStatuses"
        @create="openCreateBatch" @edit="openEditBatch" @add="addCandidate" @remove="removeBatchItem" @lock="lockBatch"
        @update-state="updateBatchState" @update-delivery="updateDelivery" />

      <!-- ============ Token 用量 ============ -->
      <section v-else-if="tab === 'usage'">
        <TokenUsage :manager="isManager" />
      </section>

      <!-- ============ 需求审核 ============ -->
      <RequirementReviewPage v-else-if="tab === 'admin' && isManager" :items="adminRequirements" :user="user"
        v-model:status="adminStatus" :statuses="reviewStatuses" :syncing="syncingGithub"
        @reload="loadAdmin" @sync="syncGithubIssues" @open="openDetail" @action="onRowAction" />

      <!-- ============ GitHub 与 Agent 集成 ============ -->
      <IntegrationSettingsPage v-else-if="tab === 'integrations' && isManager && user" :user="user" :tokens="agentTokens"
        :github-oauth-enabled="githubOauthEnabled" :mcp-url="mcpUrl" :mcp-config="mcpConfigExample" :mcp-env-config="mcpEnvConfigExample"
        @unlink-github="unlinkGithub" @link-github="startGithub('link')" @create-token="tokenDialog = true"
        @connect-token="openMcpConnection" @revoke-token="revokeToken" @copy="copyText" />

      <!-- ============ AI 模型设置 ============ -->
      <AISettingsPage v-else-if="tab === 'ai-settings' && isManager" />

      <!-- ============ 角色管理 ============ -->
      <UserManagementPage v-else-if="tab === 'users' && user?.role === 'owner'" :users="users" @toggle-role="toggleRole" />
        </div>
      </Transition>
    </main>

    <!-- ============ 页脚 ============ -->
    <footer class="footer">
      <div class="footer-inner">
        <div class="footer-brand"><img :src="logoUrl" alt="" />行影集</div>
        <div class="footer-links">
          <span>需求管理平台</span><span class="sep">·</span><a href="https://trailsnap.cn" target="_blank" rel="noopener">trailsnap.cn</a>
        </div>
      </div>
    </footer>

    <CommandPalette :open="paletteOpen" :tabs="visibleTabs" :requirements="requirements"
      @close="paletteOpen = false" @navigate="onPaletteNavigate" @open-requirement="openDetail" />

    <el-dialog v-model="analysisDialog" title="感谢你参与共创行影集" width="min(94vw, 680px)">
      <p>需求已保存，AI 会在后台分析，无需等待。你也可以现在与 AI 实时沟通，补充使用场景和细节。</p>
      <SubmissionResult v-if="submittedRequirement" :requirement="submittedRequirement" :has-receipt="!!receipts.tokenFor(submittedRequirement.id)"
        @open="openAnalyzedRequirement" @save="saveManagementLink(submittedRequirement)" @continue-a-i="continueWithAI(submittedRequirement)" />
      <template #footer><el-button @click="analysisDialog = false">稍后再聊</el-button></template>
    </el-dialog>

    <el-dialog v-model="copyDialog" :title="copyTitle" width="min(92vw, 640px)">
      <p>{{ copyHint }}</p>
      <el-input :model-value="copyValue" type="textarea" :rows="8" readonly aria-label="待复制内容" @focus="selectCopyText" />
      <template #footer><el-button @click="copyDialog = false">关闭</el-button><el-button type="primary" @click="copyText(copyValue)">复制</el-button></template>
    </el-dialog>

    <el-dialog v-model="supplementDialog" title="补充信息" width="min(92vw, 640px)" :close-on-click-modal="false" :close-on-press-escape="!supplementBusy" :show-close="!supplementBusy">
      <p>REQ-{{ supplementTarget?.public_number }} · {{ supplementTarget?.title }}</p>
      <p class="field-hint">{{ supplementTarget?.visibility === 'public' ? '补充内容将公开展示，请先移除个人照片信息、密码、密钥和未脱敏日志。' : '补充内容仅需求提交者和管理员可见。' }}补充不会改动原需求正文，范围调整由维护者评估。</p>
      <el-input v-model="supplementBody" type="textarea" :rows="6" maxlength="4000" show-word-limit aria-label="补充说明" placeholder="例如：新的复现条件、使用场景或方案调整（4–4,000 字）" />
      <p v-if="supplementError" role="alert">{{ supplementError }}。输入内容已保留，请确认后重试，避免重复提交。</p>
      <template #footer><el-button :disabled="supplementBusy" @click="supplementDialog = false">稍后继续</el-button><el-button type="primary" :loading="supplementBusy" @click="submitSupplement">保存补充说明</el-button></template>
    </el-dialog>

    <el-dialog v-model="editDialog" title="编辑需求" width="min(92vw, 640px)">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="类型" required><el-select v-model="editForm.type"><el-option label="新功能" value="feature" /><el-option label="体验优化" value="improvement" /><el-option label="问题修复" value="bug" /></el-select></el-form-item><el-form-item label="影响程度" required><el-select v-model="editForm.severity"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item></div>
        <el-form-item label="标题" required><el-input v-model="editForm.title" maxlength="160" show-word-limit /><div class="field-hint">4–160 字。</div></el-form-item>
        <el-form-item label="需求描述" required><el-input v-model="editForm.description" type="textarea" :rows="5" maxlength="8000" show-word-limit /><div class="field-hint">10–8,000 字。</div></el-form-item>
        <el-form-item label="复现步骤"><el-input v-model="editForm.steps_to_reproduce" type="textarea" :rows="3" maxlength="4000" show-word-limit /></el-form-item>
        <div class="form-grid"><el-form-item label="当前行为"><el-input v-model="editForm.current_behavior" type="textarea" :rows="3" maxlength="3000" show-word-limit /></el-form-item><el-form-item label="期望行为"><el-input v-model="editForm.expected_behavior" type="textarea" :rows="3" maxlength="3000" show-word-limit /></el-form-item></div>
        <el-form-item v-if="!anonymousEdit" label="日志文字（仅提交人和管理员可见）"><el-input v-model="editForm.log_text" type="textarea" :rows="3" maxlength="20000" show-word-limit /></el-form-item>
        <div class="form-grid"><el-form-item label="产品版本"><el-input v-model="editForm.product_version" maxlength="50" /></el-form-item><el-form-item v-if="!anonymousEdit" label="公开范围"><el-select v-model="editForm.visibility"><el-option label="公开" value="public" /><el-option label="仅提交人和管理员" value="private" /></el-select></el-form-item></div>
        <el-alert v-if="editTarget?.github_issue_number" type="info" :closable="false">保存后将异步同步 GitHub Issue 的标题、正文、类型和状态标签。</el-alert>
      </el-form>
      <template #footer><el-button @click="editDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="submitEdit">保存</el-button></template>
    </el-dialog>

    <!-- ============ 登录 ============ -->
    <el-dialog v-model="authDialog" title="登录需求平台" width="min(92vw, 440px)">
      <el-tabs v-model="authMode"><el-tab-pane label="登录" name="login" /><el-tab-pane label="注册" name="register" /></el-tabs>
      <el-form label-position="top" @submit.prevent="submitAuth">
        <el-form-item v-if="authMode === 'register'" label="用户名"><el-input v-model="authForm.username" autocomplete="username" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="authForm.email" autocomplete="email" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="authForm.password" type="password" show-password autocomplete="current-password" /><div v-if="authMode === 'register'" class="form-hint">至少 8 位字符</div></el-form-item>
        <el-button type="primary" class="w-full" :loading="busy" native-type="submit">{{ authMode === 'login' ? '登录' : '注册' }}</el-button>
        <el-divider v-if="githubOauthEnabled">或</el-divider>
        <el-button v-if="githubOauthEnabled" class="w-full" @click="startGithub('login')">使用 GitHub 登录</el-button>
      </el-form>
    </el-dialog>

    <el-dialog v-model="tokenDialog" title="创建 Agent MCP 令牌" width="min(92vw, 600px)">
      <el-form label-position="top">
        <el-form-item label="令牌名称"><el-input v-model="tokenForm.name" placeholder="例如 Codex 需求助手" /></el-form-item>
        <el-form-item label="有效期（天）"><el-input-number v-model="tokenForm.expires_in_days" :min="1" :max="365" /></el-form-item>
        <el-form-item label="Agent 角色"><el-select v-model="tokenForm.agent_role" clearable placeholder="通用管理客户端"><el-option label="编码" value="coding" /><el-option label="测试" value="testing" /><el-option label="审查" value="review" /></el-select></el-form-item>
        <el-form-item label="限制到交付任务（可选）"><el-input v-model="tokenForm.task_id" placeholder="DeliveryTask UUID；留空表示不限具体任务" /></el-form-item>
        <el-form-item label="授权作用域"><el-checkbox-group v-model="tokenForm.scopes"><el-checkbox v-for="scope in scopeOptions" :key="scope" :value="scope">{{ scope }}</el-checkbox></el-checkbox-group></el-form-item>
      </el-form>
      <el-alert v-if="createdToken" type="success" :closable="false" title="请立即复制，关闭后无法再次查看"><code class="code-block">{{ createdToken }}</code><div class="token-created-actions"><el-button @click="copyText(createdToken)">复制令牌</el-button><el-button type="primary" :icon="Connection" @click="openCreatedTokenConnection">接入</el-button></div></el-alert>
      <template #footer><el-button @click="tokenDialog = false; createdToken = ''">关闭</el-button><el-button v-if="!createdToken" type="primary" :loading="busy" @click="createToken">创建</el-button></template>
    </el-dialog>

    <el-dialog v-model="mcpConnectionDialog" title="接入 MCP 客户端" width="min(94vw, 680px)" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="完整令牌" required>
          <el-input v-model="connectionToken" type="password" show-password placeholder="粘贴以 trp_ 开头的完整令牌" autocomplete="off" />
          <div class="field-hint">平台只保存令牌哈希。历史令牌需要重新粘贴；令牌仅保留在当前弹窗内。</div>
        </el-form-item>
      </el-form>
      <div class="connection-section">
        <div class="section-title-row"><div><h3>通用 Streamable HTTP MCP</h3><p class="meta">适用于支持 JSON MCP 配置的客户端。</p></div><el-button :disabled="!connectionToken.trim()" @click="copyText(genericMcpConfig)">复制 JSON</el-button></div>
        <pre class="code-block mcp-code"><code>{{ genericMcpConfig }}</code></pre>
      </div>
      <div class="connection-section">
        <h3>Codex 设置界面</h3>
        <dl class="config-fields">
          <div><dt>URL</dt><dd>{{ mcpUrl }}</dd></div>
          <div><dt>Bearer 令牌环境变量</dt><dd>留空</dd></div>
          <div><dt>标头</dt><dd><code>Authorization</code> → <code>Bearer 完整令牌</code></dd></div>
          <div><dt>来自环境变量的标头</dt><dd>留空</dd></div>
        </dl>
      </div>
      <el-alert type="warning" :closable="false" title="配置包含完整令牌">只复制到可信客户端，不要提交到 Git 或发送给其他人；令牌泄露后请立即撤销。</el-alert>
      <template #footer><el-button @click="closeMcpConnection">关闭</el-button></template>
    </el-dialog>

    <!-- ============ 人工审核 ============ -->
    <el-dialog v-model="reviewDialog" title="人工审核" width="min(92vw, 560px)">
      <p v-if="reviewTarget"><strong>{{ reviewTarget.title }}</strong></p>
      <el-form label-position="top">
        <el-form-item label="审核结论"><el-select v-model="reviewForm.action"><el-option v-for="(label, value) in reviewActionLabels" :key="value" :label="label" :value="value" /></el-select></el-form-item>
        <el-form-item label="原因"><el-input v-model="reviewForm.reason" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="优先级"><el-select v-model="reviewForm.priority"><el-option label="低" value="low" /><el-option label="普通" value="normal" /><el-option label="高" value="high" /><el-option label="紧急" value="urgent" /></el-select></el-form-item>
        <el-form-item label="风险"><el-select v-model="reviewForm.risk_level"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item>
        <el-form-item v-if="reviewForm.action === 'duplicate'" label="主需求 ID"><el-input v-model="reviewForm.duplicate_of_id" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="reviewDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="submitReview">确认</el-button></template>
    </el-dialog>

    <!-- ============ 修改状态 ============ -->
    <el-dialog v-model="statusDialog" title="修改需求状态" width="min(92vw, 480px)">
      <p v-if="statusTarget" class="status-dialog-title">
        <strong>{{ statusTarget.title }}</strong>
        <span class="tag" :class="`s-${statusTarget.status}`">{{ statusLabel(statusTarget.status) }}</span>
      </p>
      <el-form label-position="top" @submit.prevent="submitStatusChange">
        <el-form-item label="目标状态" required>
          <el-select v-model="statusForm.status" filterable placeholder="选择目标状态">
            <el-option v-for="status in statusChangeOptions" :key="status" :label="statusLabel(status)" :value="status" />
          </el-select>
          <div class="field-hint">流转将在状态时间线中记录操作人与原因。</div>
        </el-form-item>
        <el-form-item label="变更原因" required>
          <el-input v-model="statusForm.reason" type="textarea" :rows="4" maxlength="2000" show-word-limit placeholder="请说明状态变更的原因" />
        </el-form-item>
        <el-alert v-if="statusTarget?.github_issue_number" type="info" :closable="false" show-icon title="已关联 GitHub Issue">
          状态保存后会异步同步 GitHub Issue 的状态标签与开闭状态。
        </el-alert>
      </el-form>
      <template #footer><el-button @click="statusDialog = false">取消</el-button><el-button type="primary" :loading="busy" native-type="submit" @click="submitStatusChange">保存</el-button></template>
    </el-dialog>

    <!-- ============ 创建/编辑版本批次 ============ -->
    <el-dialog v-model="batchDialog" :title="batchEditTarget ? '编辑版本批次' : '创建版本批次'" width="min(92vw, 560px)">
      <el-form label-position="top">
        <el-form-item label="版本名称" required>
          <el-input v-model="batchForm.name" maxlength="120" show-word-limit placeholder="例如：移动端体验优化" />
          <div class="field-hint">必填，2–120 字，用于说明本批次的主题。</div>
        </el-form-item>
        <el-form-item label="版本号" required>
          <el-input v-model="batchForm.version_name" maxlength="50" show-word-limit placeholder="例如 v0.15.0" />
          <div class="field-hint">必填，1–50 个字符；仅支持英文字母、数字、点、下划线和连字符。</div>
        </el-form-item>
        <el-form-item label="版本目标" required>
          <el-input v-model="batchForm.goal" type="textarea" :rows="4" maxlength="4000" show-word-limit placeholder="说明这个版本要解决的问题和预期结果" />
          <div class="field-hint">必填，4–4,000 字。</div>
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="batchForm.batch_type"><el-option label="修复" value="fix" /><el-option label="功能" value="feature" /><el-option label="重大" value="major" /><el-option label="紧急修复" value="hotfix" /></el-select>
          <div class="field-hint">选择最符合本次发布范围的版本类型。</div>
        </el-form-item>
        <el-form-item label="计划日期">
          <el-input v-model="batchForm.target_date" type="date" />
          <div class="field-hint">可选，格式为 YYYY-MM-DD。</div>
        </el-form-item>
        <el-form-item label="允许的最高风险" required>
          <el-select v-model="batchForm.max_risk_level"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select>
          <div class="field-hint">风险高于该级别的需求不能加入此版本。</div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="batchDialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="submitBatch">{{ batchEditTarget ? '保存' : '创建' }}</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  Check, Checked, Collection, Connection, DataAnalysis, Document, DocumentAdd, EditPen, FirstAidKit, Flag, Lock,
  MagicStick, Opportunity, Picture, Promotion, Setting, TrendCharts, UploadFilled,
} from '@element-plus/icons-vue'
import { ElButton, ElMessage, ElMessageBox } from 'element-plus'
import { storeToRefs } from 'pinia'
import axios from 'axios'
import logoUrl from './assets/logo.svg'
import { api, type AgentToken, type Batch, type Dashboard, type Requirement, type RequirementHistory, type RequirementSupplement, type User as ApiUser } from './api'
import SubmissionResult from './SubmissionResult.vue'
import ConversationPage from './views/conversations/ConversationPage.vue'
import IntakePage from './views/conversations/IntakePage.vue'
import RequirementContact from './components/RequirementContact.vue'
import CommandPalette from './components/CommandPalette.vue'
import NotificationConfirmPage from './views/notifications/NotificationConfirmPage.vue'
import NotificationAdminPage from './views/notifications/NotificationAdminPage.vue'
import { APP_SITE_URL, appUrl } from './runtimeBase'
import {
  requirementStatuses, reviewActionLabels,
  statusLabel,
} from './labels'
import { stageOptions, stageStatusParam, stages } from './stages'
import RequirementDetail from './RequirementDetail.vue'
import TokenUsage from './TokenUsage.vue'
import AISettingsPage from './AISettingsPage.vue'
import { useSessionStore } from './stores/session'
import { useAnonymousReceipts, newEditToken } from './stores/anonymousReceipts'
import PublicRequirementsPage from './views/requirements/PublicRequirementsPage.vue'
import DashboardPage from './views/dashboard/DashboardPage.vue'
import VersionPlanPage from './views/versions/VersionPlanPage.vue'
import RequirementReviewPage from './views/requirements/RequirementReviewPage.vue'
import UserManagementPage from './views/settings/UserManagementPage.vue'
import MyRequirementsPage from './views/requirements/MyRequirementsPage.vue'
import AppHeader from './layouts/AppHeader.vue'
import IntegrationSettingsPage from './views/settings/IntegrationSettingsPage.vue'
import { useRoute, useRouter } from 'vue-router'
import type { AppTab as Tab } from './router'

// 对外只暴露四个阶段；这里保留变量名，避免改动模板里的一堆引用。
const statusOptions = stageOptions
const reviewStatuses = ['submitted', 'triaging', 'pending_review', 'needs_information', 'candidate', 'deferred', 'rejected', 'duplicate']
const deliveryStatuses = ['not_started', 'developing', 'pr_open', 'testing', 'completed', 'blocked', 'removed']
const batchTransitions: Record<string, string[]> = {
  scope_locked: ['developing', 'blocked', 'paused', 'cancelled'], developing: ['testing', 'blocked', 'paused', 'cancelled'],
  testing: ['developing', 'release_ready', 'blocked', 'paused', 'cancelled'], release_ready: ['testing', 'published', 'blocked', 'paused', 'cancelled'],
  published: ['completed'], blocked: ['developing', 'testing', 'release_ready', 'paused', 'cancelled'],
  paused: ['developing', 'testing', 'release_ready', 'blocked', 'cancelled'], completed: [], cancelled: [],
}
const allowedBatchStatuses = (status: string) => (batchTransitions[status] || []).filter(
  next => user.value?.role === 'owner' || !['completed', 'cancelled'].includes(next),
)

const errorMessage = (error: unknown) => {
  if (!axios.isAxiosError(error)) return String(error)
  const payload = error.response?.data as { msg?: string; detail?: string; data?: { errors?: Array<{ loc?: string[]; type?: string; msg?: string }> } } | undefined
  const fieldError = payload?.data?.errors?.[0]
  if (fieldError) {
    const field = fieldError.loc?.[fieldError.loc.length - 1]
    const labels: Record<string, string> = { username: '用户名', email: '邮箱', password: '密码' }
    if (field === 'password' && fieldError.type === 'string_too_short') return '密码至少需要 8 位字符'
    return `${labels[field || ''] || field || '输入内容'}：${fieldError.msg || '格式不正确'}`
  }
  return String(payload?.msg || payload?.detail || error.message)
}

const emptyRequirementForm = () => ({
  notification_email: '', notification_opt_in: false,
  type: 'feature', title: '', description: '', log_text: '', current_behavior: '', expected_behavior: '', steps_to_reproduce: '',
  severity: 'medium', product_version: '', visibility: 'public', submitter_name: '', submitter_contact: '', environment: {} as Record<string, unknown>,
})

const route = useRoute()
const router = useRouter()
const tab = ref<Tab>((route.meta.tab as Tab | undefined) || 'assistant')
const navCollapsed = ref(false)
try { navCollapsed.value = localStorage.getItem('rp_nav_collapsed') === '1' } catch { /* Storage is optional. */ }

/* ---------- 命令面板、视图切换与主题 ---------- */
const paletteOpen = ref(false)
const isChatView = computed(() => route.name === 'requirement-intake' || route.name === 'requirement-conversation' || tab.value === 'assistant')
const viewKey = computed(() => {
  if (route.name === 'requirement-detail') return `detail-${detailRouteNumber.value ?? 'x'}`
  if (route.name === 'requirement-conversation') return `conv-${String(route.params.number)}`
  if (route.name === 'requirement-intake') return 'intake'
  if (route.name === 'notification-confirm') return 'notice-confirm'
  return tab.value
})
const navBadges = computed(() => {
  const badges: Record<string, number> = {}
  const pending = dashboard.value?.pending_review
  if (pending) badges.admin = pending
  return badges
})
const submitTypes = [
  { value: 'feature', label: '新功能', hint: '希望多一个能力', icon: Opportunity },
  { value: 'improvement', label: '体验优化', hint: '让已有功能更顺手', icon: MagicStick },
  { value: 'bug', label: '问题修复', hint: '某个地方不工作了', icon: FirstAidKit },
]
function onPaletteNavigate(target: Tab) { void switchTab(target) }
function onGlobalKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    paletteOpen.value = !paletteOpen.value
  }
}
/* 指针跟随的微光：让卡片在高亮时更有质感，纯装饰。 */
function onPointerMove(event: PointerEvent) {
  const target = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-glow]')
  if (!target) return
  const rect = target.getBoundingClientRect()
  target.style.setProperty('--mx', `${event.clientX - rect.left}px`)
  target.style.setProperty('--my', `${event.clientY - rect.top}px`)
}
const header = ref<InstanceType<typeof AppHeader> | null>(null)
const session = useSessionStore()
const receipts = useAnonymousReceipts()
// Keep the original link available until validation and durable receipt storage succeed.
const incomingEditToken = new URLSearchParams(location.hash.slice(1)).get('edit_token')
const detailCanEdit = ref(false), detailEditReason = ref('')
const detailCanSupplement = ref(false), detailSupplements = ref<RequirementSupplement[]>([]), supplementsError = ref(false)
const copyDialog = ref(false), copyValue = ref(''), copyTitle = ref(''), copyHint = ref('')
const supplementDialog = ref(false), supplementBody = ref(''), supplementBusy = ref(false), supplementError = ref('')
const supplementTarget = ref<Requirement | null>(null)
const { user, isManager } = storeToRefs(session)
const requirements = ref<Requirement[]>([]), myRequirements = ref<Requirement[]>([]), adminRequirements = ref<Requirement[]>([])
const listLoading = ref(true)
const listError = ref('')
let listRequest = 0
const batches = ref<Batch[]>([]), users = ref<ApiUser[]>([]), candidates = ref<Requirement[]>([])
const agentTokens = ref<AgentToken[]>([])
const dashboard = ref<Dashboard | null>(null), dashboardLoading = ref(false), detailHistory = ref<RequirementHistory[]>([])
const busy = ref(false), syncingGithub = ref(false), authDialog = ref(false), reviewDialog = ref(false), editDialog = ref(false), statusDialog = ref(false), batchDialog = ref(false), tokenDialog = ref(false), mcpConnectionDialog = ref(false)
const analysisDialog = ref(false)
const submittedRequirement = ref<Requirement | null>(null)
const githubOauthEnabled = ref(false), createdToken = ref(''), createdTokenId = ref(''), connectionToken = ref('')
const authMode = ref<'login' | 'register'>('login'), adminStatus = ref('pending_review')
const sortBy = ref('updated')
const detailRouteNumber = ref<number | null>(route.name === 'requirement-detail' ? Number(route.params.number) : null)
const detailLoading = ref(false), detailTarget = ref<Requirement | null>(null)
const reviewTarget = ref<Requirement | null>(null)
const statusTarget = ref<Requirement | null>(null)
const editTarget = ref<Requirement | null>(null)
const anonymousEdit = computed(() => !!editTarget.value && !isManager.value && !!receipts.tokenFor(editTarget.value.id))
const editForm = reactive({ type: 'feature', severity: 'medium', title: '', description: '', steps_to_reproduce: '', current_behavior: '', expected_behavior: '', log_text: '', product_version: '', visibility: 'public' })
const filters = reactive({ q: '', type: '', status: '' })
const authForm = reactive({ username: '', email: '', password: '' })
const requirementForm = reactive(emptyRequirementForm())
const pendingFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const reviewForm = reactive({ action: 'candidate', reason: '', priority: 'normal', risk_level: 'medium', duplicate_of_id: '' })
const statusForm = reactive({ status: '', reason: '' })
const batchForm = reactive({ name: '', version_name: '', goal: '', batch_type: 'feature', target_date: '', max_risk_level: 'high' })
const batchEditTarget = ref<Batch | null>(null)
const scopeOptions = ['requirements:read', 'requirements:write', 'requirements:review', 'versions:read', 'versions:write', 'github:write', 'specs:read', 'tasks:write', 'tasks:claim', 'runs:write', 'artifacts:write']
const tokenForm = reactive({ name: '', scopes: ['requirements:read'], expires_in_days: 90, project_key: 'trailsnap', agent_role: '', task_id: '' })
const mcpUrl = `${APP_SITE_URL}/mcp/`
const mcpConfigExample = computed(() => `[mcp_servers.trailsnap_requirements]\nurl = "${mcpUrl}"\nhttp_headers = { Authorization = "Bearer trp_替换为刚创建的完整令牌" }\ndefault_tools_approval_mode = "writes"`)
const mcpEnvConfigExample = computed(() => `[mcp_servers.trailsnap_requirements]\nurl = "${mcpUrl}"\nbearer_token_env_var = "TRAILSNAP_MCP_TOKEN"\ndefault_tools_approval_mode = "writes"`)
const genericMcpConfig = computed(() => JSON.stringify({
  mcpServers: {
    'trailsnap-feedback': {
      type: 'http',
      url: mcpUrl,
      headers: { Authorization: connectionToken.value.trim() ? `Bearer ${connectionToken.value.trim()}` : 'Bearer <完整令牌>' },
    },
  },
}, null, 2))
const candidateSelection = reactive<Record<string, string>>({})
const visibleTabs = computed(() => [
  { key: 'assistant' as Tab, label: 'AI 助手', icon: MagicStick },
  { key: 'public' as Tab, label: '公开需求', icon: Document },
  { key: 'submit' as Tab, label: '提交需求', icon: EditPen },
  { key: 'mine' as Tab, label: user.value ? '我的需求与本机记录' : '本机提交记录', icon: Collection },
  { key: 'versions' as Tab, label: '版本计划', icon: Flag },
  { key: 'dashboard' as Tab, label: '总览看板', icon: DataAnalysis },
  { key: 'usage' as Tab, label: 'Token 用量', icon: TrendCharts },
  ...(isManager.value ? [{ key: 'notifications' as Tab, label: '邮件通知', icon: Connection }] : []),
  ...(isManager.value ? [{ key: 'admin' as Tab, label: '需求审核', icon: Checked }] : []),
  ...(isManager.value ? [{ key: 'ai-settings' as Tab, label: 'AI 设置', icon: MagicStick }] : []),
  ...(isManager.value ? [{ key: 'integrations' as Tab, label: '集成设置', icon: Connection }] : []),
  ...(user.value?.role === 'owner' ? [{ key: 'users' as Tab, label: '角色管理', icon: Setting }] : []),
])

function toggleNavigation() {
  navCollapsed.value = !navCollapsed.value
  try { localStorage.setItem('rp_nav_collapsed', navCollapsed.value ? '1' : '0') } catch { /* Keep the session preference. */ }
}

// 统计口径与展示阶段一致：一个阶段 = stages 里对应的一串内部状态，互不重叠。
const stageCount = (key: string, counts: Record<string, number>) =>
  stages.find(stage => stage.key === key)?.statuses.reduce((total, status) => total + (counts[status] || 0), 0) ?? 0
// 统计来自服务端公开口径（仅公开需求、不受列表分页与筛选影响）。
const publicStatusCounts = ref<Record<string, number>>({})
async function loadPublicStats() {
  try { publicStatusCounts.value = (await api.publicDashboard()).by_status } catch { /* 统计失败时保留上一次数据，不阻塞列表。 */ }
}
const stats = computed(() => {
  const counts = publicStatusCounts.value
  return {
    total: Object.values(counts).reduce((total, value) => total + value, 0),
    planned: stageCount('planned', counts),
    developing: stageCount('building', counts),
    done: stageCount('done', counts),
  }
})
const sortedRequirements = computed(() => {
  const list = [...requirements.value]
  if (sortBy.value === 'updated') list.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  else if (sortBy.value === 'oldest') list.sort((a, b) => a.created_at.localeCompare(b.created_at))
  else list.sort((a, b) => (b.follower_count || 0) - (a.follower_count || 0))
  return list
})
const canFollow = computed(() => !!user.value && !!detailTarget.value)
const canEditSummary = computed(() => !!user.value && !!detailTarget.value && (isManager.value || detailTarget.value.created_by === user.value.id))

async function refreshDetail() {
  if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
}

async function loadRequirements() {
  const p = new URLSearchParams()
  if (filters.q) p.set('q', filters.q)
  if (filters.type) p.set('type', filters.type)
  if (filters.status) p.set('status', stageStatusParam(filters.status))
  else p.set('include_closed', 'false')
  const request = ++listRequest
  listLoading.value = true
  listError.value = ''
  try {
    const items = await api.requirements(`?${p}`)
    if (request === listRequest) requirements.value = items
  } catch {
    if (request === listRequest) listError.value = '公开需求加载失败，请重试。'
  } finally {
    if (request === listRequest) {
      listLoading.value = false
      void loadPublicStats()
    }
  }
}
async function loadMine() {
  const local = await Promise.allSettled(receipts.receipts.map(item => api.requirementByNumber(item.number)))
  const own = user.value ? await api.requirements('?mine=true') : []
  myRequirements.value = [...new Map([...own, ...local.flatMap(item => item.status === 'fulfilled' ? [item.value] : [])].map(item => [item.id, item])).values()]
}
async function loadAdmin() { if (isManager.value) adminRequirements.value = await api.requirements(adminStatus.value ? `?status=${adminStatus.value}` : '') }
async function loadDashboard() {
  dashboardLoading.value = true
  // 管理员看全量口径，访客只看公开需求口径。
  try { dashboard.value = await (isManager.value ? api.dashboard() : api.publicDashboard()) } finally { dashboardLoading.value = false }
}
async function loadBatches() { batches.value = await api.batches(); if (isManager.value) candidates.value = await api.requirements('?status=candidate&limit=100') }
async function loadUsers() { if (user.value?.role === 'owner') users.value = await api.users() }
async function loadIntegrations() { if (isManager.value) agentTokens.value = await api.agentTokens() }
async function switchTab(value: Tab) {
  if (detailRouteNumber.value) {
    detailRouteNumber.value = null
    detailTarget.value = null
    detailHistory.value = []
    await router.push({ name: value })
  }
  tab.value = value
  if (route.name !== value) await router.push({ name: value })
  await scrollActiveTab()
  try {
    if (value === 'public') await loadRequirements()
    if (value === 'mine') await loadMine()
    if (value === 'admin') await loadAdmin()
    if (value === 'dashboard') await loadDashboard()
    if (value === 'versions') await loadBatches()
    if (value === 'users') await loadUsers()
    if (value === 'integrations') await loadIntegrations()
  } catch (e) { ElMessage.error(errorMessage(e)) }
}
async function scrollActiveTab() {
  await nextTick()
  header.value?.scrollActiveIntoView()
}
async function restoreSession() {
  await session.restore()
}

async function submitAuth() {
  if (authMode.value === 'register') {
    if (!/^[A-Za-z0-9_.-]{3,50}$/.test(authForm.username)) { ElMessage.error('用户名需为 3–50 位字母、数字、点、下划线或连字符'); return }
    if (authForm.password.length < 8) { ElMessage.error('密码至少需要 8 位字符'); return }
  }
  busy.value = true
  try {
    const result = authMode.value === 'login'
      ? await api.login({ identifier: authForm.email, password: authForm.password })
      : await api.register(authForm)
    session.acceptSession(result.token, result.user)
    authDialog.value = false
    ElMessage.success('登录成功')
    await switchTab('public')
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

async function startGithub(mode: 'login' | 'link') {
  try {
    const result = await api.githubStart(mode)
    window.location.assign(result.authorize_url)
  } catch (e) { ElMessage.error(errorMessage(e)) }
}
async function unlinkGithub() {
  try {
    await ElMessageBox.confirm('解除后仍可使用邮箱密码登录，确认继续？', '解除 GitHub 绑定')
    await api.githubUnlink()
    user.value = await api.me()
    ElMessage.success('GitHub 账号已解除绑定')
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}
async function createToken() {
  if (tokenForm.name.trim().length < 2 || !tokenForm.scopes.length) { ElMessage.error('请填写名称并至少选择一个作用域'); return }
  busy.value = true
  try {
    const result = await api.createAgentToken({ ...tokenForm, agent_role: tokenForm.agent_role || null, task_id: tokenForm.task_id.trim() || null })
    createdToken.value = result.token
    createdTokenId.value = result.id
    await loadIntegrations()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}
async function revokeToken(id: string) {
  try { await ElMessageBox.confirm('撤销后 Agent 将立即失去访问权限，确认继续？', '撤销令牌'); await api.revokeAgentToken(id); await loadIntegrations(); ElMessage.success('令牌已撤销') } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}
function openMcpConnection(token: AgentToken) {
  connectionToken.value = token.id === createdTokenId.value ? createdToken.value : ''
  mcpConnectionDialog.value = true
}
function openCreatedTokenConnection() {
  connectionToken.value = createdToken.value
  mcpConnectionDialog.value = true
}
function closeMcpConnection() {
  mcpConnectionDialog.value = false
  connectionToken.value = ''
}
function selectCopyText(event: FocusEvent) { (event.target as HTMLTextAreaElement).select() }
function showCopy(value: string, title: string, hint: string) {
  copyValue.value = value; copyTitle.value = title; copyHint.value = hint; copyDialog.value = true
}
async function copyText(value: string) {
  try { await navigator.clipboard.writeText(value); ElMessage.success('已复制') }
  catch {
    if (!copyDialog.value) showCopy(value, '手动复制', '浏览器未允许自动复制，请选中下方内容后手动复制。')
    else ElMessage.warning('自动复制失败，请选中下方内容后手动复制')
  }
}
function saveManagementLink(item: Requirement) {
  const link = receipts.managementLink(item)
  if (!link) { ElMessage.warning('此浏览器没有保存该需求的修改入口'); return }
  showCopy(link, '保存修改入口', '请复制并私下保存。换设备后打开此链接可恢复修改权限；持有链接的人可以修改对应需求，请勿公开分享。')
}
function continueWithAI(item: Requirement) {
  analysisDialog.value = false
  void router.push({ name: 'requirement-conversation', params: { number: item.public_number } })
}
function openSupplement(item: Requirement) {
  if (supplementTarget.value?.id !== item.id && supplementBody.value.trim()) {
    ElMessage.warning('还有另一条需求的补充草稿，请先完成或清空后再补充其他需求'); return
  }
  supplementTarget.value = item; supplementError.value = ''; supplementDialog.value = true
}
async function submitSupplement() {
  const target = supplementTarget.value
  if (!target || supplementBusy.value) return
  const body = supplementBody.value.trim()
  if (body.length < 4) { ElMessage.warning('请填写至少 4 个字符'); return }
  supplementBusy.value = true; supplementError.value = ''
  try {
    await api.addSupplement(target.id, body, isManager.value ? undefined : receipts.tokenFor(target.id))
    supplementBody.value = ''; supplementDialog.value = false
    ElMessage.success('补充说明已保存，等待维护者评估')
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (error) { supplementError.value = errorMessage(error) }
  finally { supplementBusy.value = false }
}

function onUserCommand(command: string | number | object) {
  if (command === 'logout') logout()
  if (command === 'mine') switchTab('mine')
}
function onNotification() { ElMessage.info('暂无新通知') }

async function submitRequirement() {
  if (busy.value) return
  const titleLength = requirementForm.title.trim().length
  const descriptionLength = requirementForm.description.trim().length
  if (titleLength < 4 || titleLength > 160) { ElMessage.error('标题需要 4–160 个字符'); return }
  if (descriptionLength < 10 || descriptionLength > 8000) { ElMessage.error('需求描述需要 10–8,000 个字符'); return }
  if (requirementForm.notification_opt_in && !requirementForm.notification_email.trim()) { ElMessage.error('请填写联系邮箱，或取消订阅'); return }
  busy.value = true
  try {
    const payload = { ...requirementForm, submitter_contact: requirementForm.notification_email.trim(), notification_email: requirementForm.notification_email.trim() || null }
    let anonymousPayload: typeof payload & { client_edit_token?: string } = payload
    if (!user.value) {
      const pendingKey = 'rp_pending_submission'
      let pending: { payload: typeof anonymousPayload } | null = null
      try { pending = JSON.parse(localStorage.getItem(pendingKey) || 'null') } catch { /* Start a fresh receipt. */ }
      const { client_edit_token: _old, ...previous } = pending?.payload || {}
      anonymousPayload = {
        ...payload,
        client_edit_token: JSON.stringify(previous) === JSON.stringify(payload) && pending?.payload.client_edit_token
          ? pending.payload.client_edit_token : newEditToken(),
      }
      try { localStorage.setItem(pendingKey, JSON.stringify({ payload: anonymousPayload })) }
      catch { ElMessage.warning('浏览器无法保存记录，提交后请保存私有管理链接') }
    }
    const created = await api.createRequirement(anonymousPayload)
    if (created.edit_token) {
      if (!receipts.save(created, created.edit_token)) ElMessage.warning('需求已提交，请在详情页保存私有管理链接，以便以后修改')
      try { localStorage.removeItem('rp_pending_submission') } catch { /* Receipt is also kept in memory. */ }
    }
    submittedRequirement.value = created
    let uploadError: unknown = null
    for (const file of pendingFiles.value) {
      try { await api.uploadAttachment(created.id, file, created.upload_token || created.edit_token, !!created.edit_token && !created.upload_token) } catch (e) { uploadError = e; break }
    }
    Object.assign(requirementForm, emptyRequirementForm())
    pendingFiles.value = []
    if (fileInput.value) fileInput.value.value = ''
    analysisDialog.value = true
    if (uploadError) ElMessage.warning(`需求已提交，但有附件上传失败：${errorMessage(uploadError)}`)
    else ElMessage.success('需求已提交')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally { busy.value = false }
}

async function openAnalyzedRequirement() {
  const target = submittedRequirement.value
  analysisDialog.value = false
  if (target) await openDetail(target)
}

const allowedFilePattern = /\.(png|jpe?g|webp|txt|log|json|pdf)$/i
function addFiles(files: File[]) {
  for (const file of files) {
    if (pendingFiles.value.length >= 5) { ElMessage.warning('每条需求最多添加 5 个附件'); break }
    if (file.size > 5 * 1024 * 1024) { ElMessage.warning(`${file.name} 超过 5MB，未添加`); continue }
    if (!allowedFilePattern.test(file.name)) { ElMessage.warning(`${file.name} 的格式不受支持`); continue }
    pendingFiles.value.push(file)
  }
}
function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(Array.from(input.files || []))
  input.value = ''
}
function handlePaste(event: ClipboardEvent) {
  const images = Array.from(event.clipboardData?.items || []).filter(item => item.kind === 'file' && item.type.startsWith('image/'))
  if (!images.length) return
  const files = images.map((item, index) => {
    const blob = item.getAsFile()!
    const extension = blob.type === 'image/jpeg' ? 'jpg' : blob.type === 'image/webp' ? 'webp' : 'png'
    return new File([blob], `clipboard-${Date.now()}-${index + 1}.${extension}`, { type: blob.type })
  })
  addFiles(files)
  ElMessage.success(`已从剪贴板添加 ${files.length} 张截图`)
}
function formatBytes(size: number) { return size < 1024 * 1024 ? `${Math.ceil(size / 1024)}KB` : `${(size / 1024 / 1024).toFixed(1)}MB` }
async function downloadAttachment(requirement: Requirement, attachment: NonNullable<Requirement['attachments']>[number]) {
  try { await api.downloadAttachment(requirement.id, attachment.id, attachment.name) } catch (e) { ElMessage.error(errorMessage(e)) }
}
function saveDraft() {
  const { environment: _env, ...rest } = requirementForm
  try {
    localStorage.setItem('rp_draft', JSON.stringify(rest))
    ElMessage.success('草稿已保存，下次进入提交页可继续填写')
  } catch { ElMessage.warning('浏览器无法保存草稿，请保留当前页面') }
}

async function loadDetail(number: number) {
  detailLoading.value = true
  detailCanEdit.value = false
  detailCanSupplement.value = false
  detailSupplements.value = []
  supplementsError.value = false
  detailEditReason.value = ''
  try {
    const requirement = await api.requirementByNumber(number)
    detailTarget.value = requirement
    const token = receipts.tokenFor(requirement.id)
    if (token || (user.value && (isManager.value || requirement.created_by === user.value.id))) {
      try {
        const capability = await api.editCapability(requirement.id, isManager.value ? undefined : token)
        detailCanEdit.value = capability.can_edit
        detailCanSupplement.value = capability.can_supplement
        detailEditReason.value = capability.reason
      } catch { detailEditReason.value = '本机编辑权限已失效，可继续查看公开进度' }
    }
    detailHistory.value = await api.requirementHistory(requirement.id)
    try { detailSupplements.value = await api.supplements(requirement.id) }
    catch { supplementsError.value = true }
  } catch (e) {
    detailTarget.value = null
    detailHistory.value = []
    ElMessage.error(errorMessage(e))
  } finally { detailLoading.value = false }
}
async function openDetail(item: Requirement | number) {
  const number = typeof item === 'number' ? item : item.public_number
  if (!number) return
  detailRouteNumber.value = number
  await router.push({ name: 'requirement-detail', params: { number } })
  window.scrollTo({ top: 0, behavior: 'smooth' })
  await loadDetail(number)
}
function closeDetail() {
  detailRouteNumber.value = null
  detailTarget.value = null
  detailHistory.value = []
  void router.push({ name: tab.value })
}
function requirementLink(item: Requirement) { return appUrl(`requirements/REQ-${item.public_number}`) }
async function copyRequirementLink(item: Requirement) { await copyText(requirementLink(item)) }
async function followDetail() {
  if (!detailTarget.value) return
  if (!user.value) { authDialog.value = true; return }
  try {
    await api.followRequirement(detailTarget.value.id)
    ElMessage.success('关注状态已更新')
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) { ElMessage.error(errorMessage(e)) }
}
async function importEditReceipt(number: number, token: string) {
  try {
    const requirement = await api.requirementByNumber(number)
    await api.editCapability(requirement.id, token)
    const saved = receipts.save(requirement, token)
    if (saved && new URLSearchParams(location.hash.slice(1)).get('edit_token') === token) {
      history.replaceState(history.state, '', location.pathname + location.search)
    }
    ElMessage[saved ? 'success' : 'warning'](saved ? '已添加到本机提交记录。换设备或清除浏览器数据前，请保存修改入口。' : '本浏览器无法保存，请妥善保留原管理链接')
  } catch { ElMessage.error('管理链接无效，可继续查看需求进度') }
}
watch(() => route.fullPath, async () => {
  const number = route.name === 'requirement-detail' ? Number(route.params.number) : null
  const metaTab = route.meta.tab as Tab | undefined
  // 直接打开详情/对话链接时，同步主导航高亮，避免停留在默认页签。
  if (metaTab && route.name !== 'requirement-intake') tab.value = metaTab
  detailRouteNumber.value = number
  if (number) {
    const token = new URLSearchParams(location.hash.slice(1)).get('edit_token')
    if (token) {
      await importEditReceipt(number, token)
    }
    await loadDetail(number)
  }
  else {
    detailTarget.value = null
    detailHistory.value = []
    tab.value = (route.meta.tab as Tab | undefined) || 'assistant'
  }
})

function openEdit(item: Requirement) {
  editTarget.value = item
  Object.assign(editForm, {
    type: item.type, severity: item.severity, title: item.title, description: item.description,
    steps_to_reproduce: item.steps_to_reproduce || '', log_text: item.log_text || '',
    current_behavior: item.current_behavior || '', expected_behavior: item.expected_behavior || '',
    product_version: item.product_version || '', visibility: item.visibility,
  })
  editDialog.value = true
}
async function submitEdit() {
  if (!editTarget.value) return
  if (editForm.title.trim().length < 4 || editForm.description.trim().length < 10) { ElMessage.error('请按要求填写标题和需求描述'); return }
  busy.value = true
  try {
    const { visibility, log_text, ...publicFields } = editForm
    const fields = anonymousEdit.value ? publicFields : { ...publicFields, visibility, log_text }
    const updated = await api.updateRequirement(editTarget.value.id, {
      ...fields, title: editForm.title.trim(), description: editForm.description.trim(),
      expected_state_version: editTarget.value.state_version,
    }, anonymousEdit.value ? receipts.tokenFor(editTarget.value.id) : undefined)
    editDialog.value = false
    ElMessage.success(updated.github_issue_number ? '需求已保存，GitHub Issue 将自动同步' : '需求已保存')
    await refreshManaged()
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) {
    if (axios.isAxiosError(e) && e.response?.status === 409) {
      ElMessage.warning('需求内容或处理状态已变化，请关闭编辑窗口并刷新后重新修改')
    } else ElMessage.error(errorMessage(e))
  } finally { busy.value = false }
}

function onRowAction(payload: { item: Requirement; command: string }) {
  const { item, command } = payload
  if (command === 'follow') follow(item)
  else if (command === 'review') openReview(item)
  else if (command === 'edit') openEdit(item)
  else if (command === 'status') openStatusChange(item)
  else if (command === 'withdraw') withdraw(item)
  else if (command === 'github-create') createGithubIssue(item)
  else if (command === 'github-link') linkGithubIssue(item)
  else if (command === 'github-close') closeGithubIssue(item)
  else if (command === 'github-unlink') unlinkGithubIssue(item)
  else if (command === 'close') closeManagedRequirement(item)
  else if (command === 'delete') deleteManagedRequirement(item)
}

async function promptReason(title: string) {
  const result = await ElMessageBox.prompt('请输入操作原因（将写入审计记录）', title, { inputPattern: /.{2,}/, inputErrorMessage: '至少输入两个字符' })
  return result.value
}
async function refreshManaged() { await Promise.all([loadAdmin(), loadRequirements()]) }
async function syncGithubIssues() {
  syncingGithub.value = true
  try {
    const result = await api.syncGithubIssues()
    ElMessage.success(`同步完成：新增 ${result.created} 条，更新 ${result.updated} 条，跳过 ${result.skipped} 条`)
    await refreshManaged()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { syncingGithub.value = false }
}
async function createGithubIssue(item: Requirement) { try { await ElMessageBox.confirm('确认在配置的 TrailSnap 仓库中新建 Issue？', '新建 GitHub Issue'); await api.createGithubIssue(item.id); ElMessage.success('GitHub Issue 已创建并关联'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function linkGithubIssue(item: Requirement) { try { const result = await ElMessageBox.prompt('请输入 GitHub Issue 编号', '关联已有 Issue', { inputPattern: /^\d+$/, inputErrorMessage: '请输入正整数' }); await api.linkGithubIssue(item.id, Number(result.value)); ElMessage.success('Issue 已关联'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function closeGithubIssue(item: Requirement) { try { const reason = await promptReason('关闭 GitHub Issue 与需求'); await api.closeGithubIssue(item.id, reason); ElMessage.success('Issue 与需求均已关闭'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function unlinkGithubIssue(item: Requirement) { try { await ElMessageBox.confirm('只解除平台关联，不会修改 GitHub Issue，确认继续？', '取消 Issue 关联'); await api.unlinkGithubIssue(item.id); ElMessage.success('已解除关联'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function closeManagedRequirement(item: Requirement) { try { const reason = await promptReason('关闭需求'); await api.closeRequirement(item.id, reason); ElMessage.success('需求已关闭'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }
async function deleteManagedRequirement(item: Requirement) { try { const reason = await promptReason('删除需求（可恢复）'); await ElMessageBox.confirm(`确认删除“${item.title}”？数据会保留以供审计和恢复。`, '二次确认', { type: 'warning' }); await api.deleteRequirement(item.id, reason); ElMessage.success('需求已删除'); await refreshManaged() } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) } }

async function follow(item: Requirement) {
  if (!user.value) { authDialog.value = true; return }
  try {
    await api.followRequirement(item.id)
    ElMessage.success('关注状态已更新')
    await switchTab(tab.value)
  } catch (e) { ElMessage.error(errorMessage(e)) }
}

async function withdraw(item: Requirement) {
  try {
    await ElMessageBox.confirm('撤回后该需求将不再展示在公开列表，确认撤回？', '撤回需求')
    await api.withdrawRequirement(item.id)
    ElMessage.success('需求已撤回')
    await switchTab(tab.value)
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

function openReview(item: Requirement) {
  reviewTarget.value = item
  Object.assign(reviewForm, { action: 'candidate', reason: '', priority: item.priority || 'normal', risk_level: item.risk_level || 'medium', duplicate_of_id: '' })
  reviewDialog.value = true
}

async function submitReview() {
  if (!reviewTarget.value) return
  busy.value = true
  try {
    await api.review(reviewTarget.value.id, reviewForm)
    reviewDialog.value = false
    ElMessage.success('审核结果已保存')
    await loadAdmin()
    await loadRequirements()
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

// 常用流转：按当前状态给出推荐的下一步，供弹窗默认展示；其余状态仍可通过筛选选择。
const suggestedStatusTransitions: Record<string, string[]> = {
  submitted: ['pending_review', 'needs_information', 'rejected', 'closed'],
  triaging: ['pending_review', 'needs_information', 'rejected', 'closed'],
  pending_review: ['candidate', 'needs_information', 'deferred', 'rejected', 'closed'],
  needs_information: ['submitted', 'pending_review', 'rejected', 'closed'],
  candidate: ['scheduled', 'developing', 'deferred', 'rejected', 'closed'],
  scheduled: ['developing', 'testing', 'candidate', 'closed'],
  developing: ['testing', 'release_ready', 'closed'],
  testing: ['developing', 'release_ready', 'closed'],
  release_ready: ['released', 'testing', 'closed'],
  released: ['closed'],
  deferred: ['pending_review', 'candidate', 'closed'],
  rejected: ['pending_review', 'closed'],
  duplicate: ['pending_review', 'closed'],
  withdrawn: ['pending_review', 'closed'],
  closed: ['pending_review'],
}
const statusChangeOptions = computed(() => {
  if (!statusTarget.value) return requirementStatuses
  const current = statusTarget.value.status
  const suggested = (suggestedStatusTransitions[current] || []).filter(status => status !== current)
  const rest = requirementStatuses.filter(status => status !== current && !suggested.includes(status))
  return [...suggested, ...rest]
})

function openStatusChange(item: Requirement) {
  statusTarget.value = item
  Object.assign(statusForm, {
    status: (suggestedStatusTransitions[item.status] || requirementStatuses.filter(s => s !== item.status))[0] || '',
    reason: '',
  })
  statusDialog.value = true
}

async function submitStatusChange() {
  if (!statusTarget.value) return
  if (!statusForm.status) { ElMessage.error('请选择目标状态'); return }
  if (statusForm.reason.trim().length < 2) { ElMessage.error('请填写至少 2 个字符的变更原因'); return }
  busy.value = true
  try {
    const updated = await api.updateRequirementStatus(statusTarget.value.id, statusForm.status, statusForm.reason.trim())
    statusDialog.value = false
    ElMessage.success(updated.github_issue_number ? '状态已更新，GitHub Issue 将自动同步' : '状态已更新')
    await refreshManaged()
    if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

const emptyBatchForm = () => ({ name: '', version_name: '', goal: '', batch_type: 'feature', target_date: '', max_risk_level: 'high' })

function openCreateBatch() {
  batchEditTarget.value = null
  Object.assign(batchForm, emptyBatchForm())
  batchDialog.value = true
}

function openEditBatch(batch: Batch) {
  batchEditTarget.value = batch
  Object.assign(batchForm, {
    name: batch.name, version_name: batch.version_name, goal: batch.goal,
    batch_type: batch.batch_type, target_date: batch.target_date || '', max_risk_level: batch.max_risk_level,
  })
  batchDialog.value = true
}

async function submitBatch() {
  const name = batchForm.name.trim()
  const versionName = batchForm.version_name.trim()
  const goal = batchForm.goal.trim()
  if (name.length < 2 || name.length > 120) { ElMessage.error('版本名称需要 2–120 个字符'); return }
  if (!/^[A-Za-z0-9._-]{1,50}$/.test(versionName)) { ElMessage.error('版本号只能包含 1–50 个英文字母、数字、点、下划线或连字符'); return }
  if (goal.length < 4 || goal.length > 4000) { ElMessage.error('版本目标需要 4–4,000 个字符'); return }
  const payload = { name, version_name: versionName, goal, batch_type: batchForm.batch_type, target_date: batchForm.target_date || null, max_risk_level: batchForm.max_risk_level }
  busy.value = true
  try {
    if (batchEditTarget.value) {
      await api.updateBatch(batchEditTarget.value.id, payload)
      batchDialog.value = false
      ElMessage.success('版本批次已更新')
    } else {
      await api.createBatch(payload)
      batchDialog.value = false
      Object.assign(batchForm, emptyBatchForm())
      ElMessage.success('版本批次已创建')
    }
    await loadBatches()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { busy.value = false }
}

async function addCandidate(batchId: string) {
  const id = candidateSelection[batchId]
  if (!id) return
  try { await api.addBatchItem(batchId, id); candidateSelection[batchId] = ''; await loadBatches() } catch (e) { ElMessage.error(errorMessage(e)) }
}

async function removeBatchItem(batchId: string, itemId: string) {
  try {
    await ElMessageBox.confirm('确认将该需求移出版本？', '确认')
    await api.removeBatchItem(batchId, itemId)
    await loadBatches()
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

async function lockBatch(batchId: string) {
  try {
    await ElMessageBox.confirm('锁定后需求范围将生成快照，确认继续？', '锁定版本范围')
    await api.lockBatch(batchId)
    ElMessage.success('版本范围已锁定')
    await loadBatches()
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

async function updateBatchState(batchId: string, status: string) {
  try {
    const reason = await ElMessageBox.prompt('请输入状态变更原因', '更新版本状态', { inputPattern: /.{2,}/, inputErrorMessage: '至少输入两个字符' })
    await api.updateBatchStatus(batchId, status, reason.value)
    await loadBatches()
  } catch (e) { if (e !== 'cancel') ElMessage.error(errorMessage(e)) }
}

async function updateDelivery(batchId: string, itemId: string, status: string) {
  try { await api.updateDeliveryStatus(batchId, itemId, status); await loadBatches() } catch (e) { ElMessage.error(errorMessage(e)) }
}

async function toggleRole(row: ApiUser) {
  try { await api.updateRole(row.id, row.role === 'admin' ? 'viewer' : 'admin'); await loadUsers() } catch (e) { ElMessage.error(errorMessage(e)) }
}

function logout() {
  session.clear()
  void switchTab('assistant')
  void loadRequirements()
}

onMounted(async () => {
  // 首次导航完成前 route 可能仍是初始值，这里以当前路由为准修正页签。
  const initialTab = route.meta.tab as Tab | undefined
  if (initialTab && route.name !== 'requirement-intake') tab.value = initialTab
  const params = new URLSearchParams(window.location.search)
  if (incomingEditToken && detailRouteNumber.value) {
    await importEditReceipt(detailRouteNumber.value, incomingEditToken)
  }
  try { githubOauthEnabled.value = (await api.authStatus()).github_oauth_enabled } catch { githubOauthEnabled.value = false }
  const githubError = params.get('github_error')
  if (githubError) {
    const message = githubError === 'oauth_upstream'
      ? 'GitHub 登录暂时失败，请重新发起登录；若持续出现，请管理员检查服务端 OAuth 日志和 Client Secret。'
      : 'GitHub 登录失败，请重试。'
    ElMessage.error({ message, duration: 8000 })
    params.delete('github_error')
    history.replaceState({}, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`)
  }
  const githubGrant = params.get('github_grant')
  if (githubGrant) {
    try {
      const result = await api.githubRedeem(githubGrant)
      session.acceptSession(result.token, result.user)
      ElMessage.success('GitHub 登录或绑定成功')
    } catch (e) { ElMessage.error(errorMessage(e)) }
    params.delete('github_grant')
    history.replaceState({}, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`)
  }
  const requestedTab = params.get('view') as Tab | null
  if (requestedTab && ['public', 'dashboard', 'submit', 'assistant', 'mine', 'admin', 'versions', 'usage', 'integrations', 'ai-settings', 'users'].includes(requestedTab)) tab.value = requestedTab
  const requestedType = params.get('type')
  if (requestedType && ['bug', 'improvement', 'feature'].includes(requestedType)) requirementForm.type = requestedType
  if (tab.value === 'submit') {
    try {
      const draft = localStorage.getItem('rp_draft')
      if (draft) Object.assign(requirementForm, JSON.parse(draft))
    } catch { /* Invalid or unavailable drafts must not block feedback. */ }
  }
  if (!user.value) await restoreSession()
  if ((['admin', 'integrations', 'ai-settings'].includes(tab.value) && !isManager.value) || (tab.value === 'users' && user.value?.role !== 'owner')) tab.value = 'assistant'
  await Promise.all([loadRequirements(), loadBatches()])
  if (tab.value === 'mine') await loadMine()
  if (tab.value === 'admin') await loadAdmin()
  if (tab.value === 'dashboard') await loadDashboard()
  if (tab.value === 'users') await loadUsers()
  if (tab.value === 'integrations') await loadIntegrations()
  if (detailRouteNumber.value) await loadDetail(detailRouteNumber.value)
  await scrollActiveTab()
  window.addEventListener('keydown', onGlobalKeydown)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('pointermove', onPointerMove)
})
</script>

