<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import "element-plus/es/components/message/style/css";
import {
  api,
  ApiError,
  checkResponse,
  type Conversation,
  type Message,
} from "./api";
import AdminLayout from "./layouts/AdminLayout.vue";
import { roleRows } from "./domain/roles";
import { formatLocalDateTime } from "./domain/datetime";
import { conversationStatusLabels, messageSenderLabels } from "./domain/conversationLabels";
import "./admin.css";
import "./login.css";
import { withBrowserIdentity } from "./browserIdentity";
import brandLogo from "./assets/customer-service-logo.png";

const savedMode = localStorage.getItem("workbenchMode");
const mode = ref<"customer" | "agent" | "admin">(
  savedMode === "admin" || savedMode === "agent" ? savedMode : "customer",
);
const customerToken = ref(localStorage.getItem("customerToken") || "");
const selectedAccountId = ref(Number(localStorage.getItem('customerAccountId')) || 1);
const customerAccounts = ref<{id:number; name:string; platform_name:string; commerce_enabled:boolean}[]>([]);
watch(selectedAccountId, value => localStorage.setItem('customerAccountId', String(value)));
async function loadCustomerAccounts() {
  if (!customerToken.value) return;
  customerAccounts.value = await api<typeof customerAccounts.value>('/api/customer/accounts', 'GET', undefined, customerToken.value);
  if (!customerAccounts.value.some(row => row.id === selectedAccountId.value))
    selectedAccountId.value = customerAccounts.value[0]?.id || 1;
}
type UnifiedUser = {
  id: number;
  kind: string;
  user_type: string;
  username: string;
  role: string;
  display_name: string;
  email?: string | null;
  active: boolean;
};
const customerUser = ref<UnifiedUser | null>(null);
const customerReady = ref(false);
const identityBusy = ref(false);
const staffUser = ref<UnifiedUser | null>(null);
const loginVisible = ref(true);
const bootstrapping = ref(true);
const currentUser = computed(() =>
  mode.value === "customer" ? customerUser.value : staffUser.value,
);
const currentRoleName = computed(
  () =>
    roleRows.find((r) => r.role === currentUser.value?.role)?.name ||
    currentUser.value?.role ||
    "",
);
const currentTypeName = computed(() => currentUser.value?.user_type === 'B' ? '商户端' : '客户端');
const profileInitial = computed(() => (currentUser.value?.display_name || currentUser.value?.username || '用').slice(0, 1).toUpperCase());
const profileVisible = ref(false);
const helpVisible = ref(false);
function accountCommand(command: string) {
  if (command === 'profile') profileVisible.value = true;
  else if (command === 'help') helpVisible.value = true;
  else if (command === 'logout') switchLogin();
}
function switchLogin() {
  resetIdentity("customer");
  resetIdentity("staff");
  staffUser.value = null;
  loginVisible.value = true;
  password.value = "";
  localStorage.setItem("sessionKind", "entry");
}

const ordersVisible = ref(false);
const myOrders = ref<
  {
    order_id: string;
    user_id: number;
    status: string;
    amount: string;
    product_sku: string;
  }[]
>([]);
const staffToken = ref(localStorage.getItem("staffToken") || "");
const email = ref("");
const password = ref("");
const role = ref(localStorage.getItem("staffRole") || "");
const conversations = ref<Conversation[]>([]);
const current = ref<Conversation | null>(null);
const messages = ref<Message[]>([]);
const messagesContainer = ref<HTMLElement | null>(null);
const draft = ref("");
const sending = ref(false);
const aiTyping = ref(false);
const actions = ref<{ id: number; action: string; order_id: string }[]>([]);
const isAdmin = computed(() => ["SUPER_ADMIN", "ADMIN"].includes(role.value));
const canOperateSupport = computed(
  () => isAdmin.value || role.value === "CUSTOMER_SERVICE",
);
async function enterEshopCustomer(token: string, name: string, accountId?: number) {
  resetIdentity("customer");
  customerToken.value = token;
  mode.value = "customer";
  await saveCustomerToken();
  if (accountId) selectedAccountId.value = accountId;
  loginVisible.value = false;
  localStorage.setItem("sessionKind", "customer");
  ElMessage.success(`已切换为客户：${name}`);
}
let socket: WebSocket | null = null;
let socketGeneration = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
const activeToken = computed(() =>
  mode.value === "customer" ? customerToken.value : staffToken.value,
);
const canSend = computed(
  () =>
    !!current.value &&
    (mode.value === "customer" ||
      (current.value.current_agent_id === staffUser.value?.id &&
        current.value.status === "HUMAN_ACTIVE")),
);
function scrollMessagesToBottom() {
  nextTick(() => {
    const container = messagesContainer.value;
    if (container) container.scrollTop = container.scrollHeight;
  });
}
watch(messages, scrollMessagesToBottom, { deep: true, flush: "post" });
watch(aiTyping, scrollMessagesToBottom, { flush: "post" });
async function saveCustomerToken() {
  customerToken.value = customerToken.value.trim();
  if (!customerToken.value) {
    ElMessage.warning("请先填写用户令牌");
    return;
  }
  try {
    const profile = await api<UnifiedUser>(
      "/api/auth/me",
      "GET",
      undefined,
      customerToken.value,
    );
    if (!["CUSTOMER", "GUEST"].includes(profile.kind))
      throw new Error("请使用顾客或游客令牌");
    customerUser.value = profile;
    localStorage.setItem("sessionUserKind", profile.kind);
    localStorage.setItem("customerToken", customerToken.value);
    customerReady.value = true;
    await loadCustomerAccounts();
    await loadConversations();
  } catch (e) {
    notifyError(e);
  }
}
async function guestLogin(enter = true) {
  if (identityBusy.value) return;
  identityBusy.value = true;
  try {
    await withBrowserIdentity(async (identity) => {
      const result = await api<{
        access_token: string;
        visitor_id: string;
        user: UnifiedUser;
      }>(
        "/api/auth/guest-session",
        "POST",
        identity,
        customerToken.value || undefined,
      );
      localStorage.setItem("visitorId", result.visitor_id);
      resetIdentity("customer");
      customerToken.value = result.access_token;
      customerUser.value = result.user;
      localStorage.setItem("customerToken", result.access_token);
      customerReady.value = true;
      await loadCustomerAccounts();
      localStorage.setItem("sessionUserKind", "GUEST");
      if (enter) {
        mode.value = "customer";
        loginVisible.value = false;
        localStorage.setItem("sessionKind", "customer");
        await loadConversations();
      } else localStorage.setItem("sessionKind", "entry");
    });
  } catch (e) {
    notifyError(e);
  } finally {
    identityBusy.value = false;
  }
}
async function restoreSession() {
  try {
    const staffFirst =
      localStorage.getItem("sessionKind") === "staff" ||
      (!localStorage.getItem("sessionKind") && mode.value !== "customer");
    if (staffFirst && staffToken.value) {
      staffUser.value = await api<UnifiedUser>(
        "/api/auth/me",
        "GET",
        undefined,
        staffToken.value,
      );
      if (staffUser.value.user_type !== "B") throw new Error("商家身份不匹配");
      role.value = staffUser.value.role;
      mode.value = role.value === "CUSTOMER_SERVICE" ? "agent" : "admin";
      loginVisible.value = false;
      if (mode.value !== "admin") await loadConversations();
    } else if (
      customerToken.value &&
      localStorage.getItem("sessionKind") !== "entry"
    ) {
      mode.value = "customer";
      await saveCustomerToken();
      if (customerReady.value) {
        mode.value = "customer";
        loginVisible.value = false;
        if (customerUser.value?.kind === "GUEST") await guestLogin(true);
        else await loadConversations();
      }
    }
    if (loginVisible.value && !customerToken.value)
      await guestLogin(
        localStorage.getItem("sessionKind") === "customer" &&
          localStorage.getItem("sessionUserKind") === "GUEST",
      );
  } catch (e) {
    notifyError(e);
  } finally {
    bootstrapping.value = false;
  }
}
async function loadMyOrders() {
  try {
    myOrders.value = await api<typeof myOrders.value>(
      `/api/customer/orders?account_id=${selectedAccountId.value}`,
      "GET",
      undefined,
      customerToken.value,
    );
    ordersVisible.value = true;
  } catch (e) {
    notifyError(e);
  }
}
function resetIdentity(
  kind: "customer" | "staff" = mode.value === "customer" ? "customer" : "staff",
) {
  if ((mode.value === "customer") === (kind === "customer")) {
    socketGeneration++;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
    socket = null;
    current.value = null;
    messages.value = [];
    conversations.value = [];
    actions.value = [];
  }
  if (kind === "customer") {
    customerToken.value = "";
    customerUser.value = null;
    customerReady.value = false;
    ordersVisible.value = false;
    myOrders.value = [];
    localStorage.removeItem("customerToken");
    localStorage.removeItem("customerName");
  } else {
    staffUser.value = null;
    staffToken.value = "";
    role.value = "";
    localStorage.removeItem("staffToken");
    localStorage.removeItem("staffRole");
  }
}

function notifyError(error: unknown) {
  if (error instanceof ApiError && error.status === 401 && error.token) {
    // Ignore late failures from a token that has already been replaced or cleared.
    if (error.token === customerToken.value) resetIdentity("customer");
    else if (error.token === staffToken.value) resetIdentity("staff");
    else return;
    loginVisible.value = true;
    ElMessage.warning("登录已失效，请从统一入口重新登录");
    return;
  }
  ElMessage.error(error instanceof Error ? error.message : String(error));
}
async function login() {
  if (identityBusy.value) return;
  identityBusy.value = true;
  try {
    const result = await api<{
      access_token: string;
      role: string;
      user: UnifiedUser;
    }>("/api/auth/login", "POST", {
      account: email.value,
      password: password.value,
    });
    resetIdentity("customer");
    resetIdentity("staff");
    password.value = "";
    if (result.user.user_type === "C") {
      customerToken.value = result.access_token;
      mode.value = "customer";
      await saveCustomerToken();
      localStorage.setItem("sessionKind", "customer");
    } else {
      staffToken.value = result.access_token;
      staffUser.value = result.user;
      role.value = result.role;
      localStorage.setItem("staffToken", result.access_token);
      localStorage.setItem("staffRole", result.role);
      localStorage.setItem("sessionKind", "staff");
      mode.value = result.role === "CUSTOMER_SERVICE" ? "agent" : "admin";
      if (mode.value !== "admin") await loadConversations();
    }
    loginVisible.value = false;
  } catch (e) {
    notifyError(e);
  } finally {
    identityBusy.value = false;
  }
}
async function loadConversations() {
  if (!activeToken.value) return;
  try {
    conversations.value = await api<Conversation[]>(
      mode.value === "customer"
        ? "/api/customer/conversations"
        : "/api/agent/conversations",
      "GET",
      undefined,
      activeToken.value,
    );
  } catch (e) {
    notifyError(e);
  }
}
async function createConversation() {
  try {
    const conversation = await api<Conversation>(
      "/api/customer/conversations",
      "POST",
      { account_id: selectedAccountId.value },
      customerToken.value,
    );
    await loadConversations();
    await selectConversation(conversation);
  } catch (e) {
    notifyError(e);
  }
}
async function selectConversation(conversation: Conversation) {
  current.value = conversation;
  try {
    messages.value = await api<Message[]>(
      `${mode.value === "customer" ? "/api/customer" : "/api/agent"}/conversations/${conversation.id}/messages`,
      "GET",
      undefined,
      activeToken.value,
    );
    if (mode.value === "customer") await loadActions();
    if (current.value && activeToken.value) connectSocket();
  } catch (e) {
    notifyError(e);
  }
}
function connectSocket() {
  const generation = ++socketGeneration;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  socket?.close();
  socket = null;
  if (!current.value || !activeToken.value) return;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(
    `${scheme}//${location.host}/ws/conversations/${current.value.id}`,
  );
  socket.onopen = () =>
    socket?.send(
      JSON.stringify({
        token: activeToken.value,
        after_id: messages.value.at(-1)?.id || 0,
      }),
    );
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data) as Message;
    if (!messages.value.some((m) => m.id === message.id))
      messages.value.push(message);
  };
  socket.onclose = async (event) => {
    if (generation !== socketGeneration) return;
    if (event.code === 1008) {
      await loadConversations();
      if (generation === socketGeneration && activeToken.value)
        ElMessage.error("无法连接当前会话，请刷新会话列表后重试");
      return;
    }
    if (generation === socketGeneration && current.value)
      reconnectTimer = setTimeout(connectSocket, 1500);
  };
}
async function send() {
  if (!current.value || !draft.value.trim()) return;
  const content = draft.value.trim();
  draft.value = "";
  sending.value = true;
  aiTyping.value = mode.value === "customer" && current.value.status === "AI_ACTIVE";
  try {
    if (mode.value === "customer") await sendStream(current.value.id, content);
    else
      await api(
        `/api/agent/conversations/${current.value.id}/messages`,
        "POST",
        { content },
        activeToken.value,
      );
    if (current.value) await selectConversation(current.value);
  } catch (e) {
    notifyError(e);
    if (mode.value === "customer" && current.value)
      await selectConversation(current.value);
    else draft.value = content;
  } finally {
    aiTyping.value = false;
    sending.value = false;
  }
}
async function sendStream(conversationId: number, content: string) {
  const requestToken = customerToken.value;
  const response = await fetch(
    `/api/customer/conversations/${conversationId}/messages/stream`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${requestToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content }),
    },
  );
  await checkResponse(response, requestToken);
  if (!response.body) throw new Error("消息发送失败");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let partial: Message | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let separator: number;
    while ((separator = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      if (!frame.startsWith("data: ")) continue;
      const event = JSON.parse(frame.slice(6));
      if (event.type === "error") {
        aiTyping.value = false;
        throw new Error(event.detail);
      }
      if (
        event.type === "message" &&
        !messages.value.some((m) => m.id === event.message.id)
      )
        messages.value.push(event.message);
      if (event.type === "delta") {
        aiTyping.value = false;
        if (!partial) {
          partial = {
            id: -Date.now(),
            sender_type: "AI",
            content: "",
            citations: [],
            created_at: new Date().toISOString(),
          };
          messages.value.push(partial);
        }
          const livePartial = messages.value.find((message) => message.id === partial?.id);
          if (livePartial) livePartial.content += event.content;
      }
      if (event.type === "done" && event.reply) {
        aiTyping.value = false;
        messages.value = messages.value.filter((m) => m.id !== partial?.id);
        if (!messages.value.some((m) => m.id === event.reply.id))
          messages.value.push(event.reply);
      }
      if (event.type === "done" && event.conversation) {
        aiTyping.value = false;
        current.value = event.conversation;
      }
    }
  }
}
async function handoff() {
  if (!current.value) return;
  try {
    current.value = await api<Conversation>(
      `/api/customer/conversations/${current.value.id}/handoff`,
      "POST",
      {},
      customerToken.value,
    );
    await loadConversations();
  } catch (e) {
    notifyError(e);
  }
}
async function claim() {
  if (!current.value) return;
  try {
    current.value = await api<Conversation>(
      `/api/agent/conversations/${current.value.id}/claim`,
      "POST",
      {},
      staffToken.value,
    );
    await loadConversations();
  } catch (e) {
    notifyError(e);
  }
}
async function closeConversation() {
  if (!current.value) return;
  try {
    current.value = await api<Conversation>(
      `/api/agent/conversations/${current.value.id}/close`,
      "POST",
      {},
      staffToken.value,
    );
    await loadConversations();
  } catch (e) {
    notifyError(e);
  }
}
async function loadActions() {
  if (!current.value) return;
  try {
    actions.value = await api(
      `/api/customer/conversations/${current.value.id}/actions`,
      "GET",
      undefined,
      customerToken.value,
    );
  } catch (e) {
    notifyError(e);
  }
}
async function confirmAction(id: number, confirm: boolean) {
  try {
    const result = await api<{ status: string }>(
      `/api/customer/actions/${id}/confirm`,
      "POST",
      { confirm },
      customerToken.value,
    );
    ElMessage.info(result.status);
    await loadActions();
    if (current.value) await selectConversation(current.value);
  } catch (e) {
    notifyError(e);
  }
}
async function feedback(id: number, rating: number) {
  try {
    await api(
      `/api/customer/messages/${id}/feedback`,
      "POST",
      { rating, reason: rating < 0 ? "not_answered" : "" },
      customerToken.value,
    );
    ElMessage.success("反馈已提交");
  } catch (e) {
    notifyError(e);
  }
}
watch(mode, async () => {
  localStorage.setItem("workbenchMode", mode.value);
  socketGeneration++;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  socket?.close();
  current.value = null;
  messages.value = [];
  if (mode.value !== "admin") await loadConversations();
});
onMounted(restoreSession);
onUnmounted(() => {
  socketGeneration++;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  socket?.close();
});
</script>

<template>
  <div class="shell">
    <header class="app-header">
      <div class="app-brand">
        <div class="brand-title">
          <img class="brand-logo" :src="brandLogo" alt="电商智能客服" />
          <strong>电商智能客服</strong>
          <el-tag v-if="!loginVisible && currentUser" size="small" effect="light">{{ currentTypeName }}</el-tag>
        </div>
        <small>单商户工作台</small>
      </div>
      <div v-if="!loginVisible" class="account-toolbar">
        <el-select v-if="currentUser?.user_type === 'C'" v-model="selectedAccountId"
          placeholder="选择咨询账号" style="width:210px">
          <el-option v-for="account in customerAccounts" :key="account.id"
            :label="`${account.platform_name} · ${account.name}`" :value="account.id" />
        </el-select>
        <el-button v-if="currentUser?.user_type === 'C'" @click="loadMyOrders"
          >我的订单</el-button
        ><el-button
          v-if="
            currentUser?.user_type === 'B' &&
            canOperateSupport &&
            mode === 'admin'
          "
          class="workspace-switch"
          @click="mode = 'agent'"
          >客服工作台</el-button
        ><el-button
          v-if="
            currentUser?.user_type === 'B' &&
            role !== 'CUSTOMER_SERVICE' &&
            mode === 'agent'
          "
          class="workspace-switch"
          @click="mode = 'admin'"
          >运营后台</el-button
        >
        <div class="profile-area">
          <span class="profile-avatar" aria-hidden="true">{{ profileInitial }}</span>
          <el-dropdown class="profile-dropdown" trigger="click" @command="accountCommand">
            <button class="profile-trigger" type="button">
              <span class="profile-copy"><strong>{{ currentUser?.display_name || currentUser?.username }}</strong><span class="profile-role">· {{ currentRoleName }}</span></span>
              <span class="profile-chevron">⌄</span>
            </button>
            <template #dropdown><el-dropdown-menu>
              <el-dropdown-item command="profile">♙　用户中心</el-dropdown-item>
              <el-dropdown-item command="help">?　使用帮助</el-dropdown-item>
              <el-dropdown-item divided command="logout">↪　退出登录</el-dropdown-item>
            </el-dropdown-menu></template>
          </el-dropdown>
        </div>
      </div>
    </header>
    <main v-if="bootstrapping" class="login-stage"><p>正在恢复登录…</p></main>
    <main v-else-if="loginVisible" class="login-stage">
      <section class="login-card">
        <div class="login-intro">
          <div class="login-heading"><img class="brand-logo login-mark" :src="brandLogo" alt="电商智能客服" /><h1>登录工作台</h1></div>
          <p>客户、客服和运营使用同一个登录入口</p>
        </div>
        <el-form label-position="top" @submit.prevent="login"
          ><el-form-item label="用户名 / 邮箱"
            ><el-input
              v-model="email"
              autocomplete="username"
              placeholder="客户用户名或员工邮箱" /></el-form-item
          ><el-form-item label="密码"
            ><el-input
              v-model="password"
              type="password"
              autocomplete="current-password"
              show-password
              placeholder="请输入密码"
              @keyup.enter="login" /></el-form-item
          ><el-button
            class="login-primary"
            type="primary"
            :loading="identityBusy"
            :disabled="!email.trim() || !password"
            @click="login"
            >登录</el-button
          ></el-form
        >
        <div class="login-divider">也可以</div>
        <el-button
          class="guest-entry"
          :loading="identityBusy"
          @click="guestLogin(true)"
          >以游客身份咨询</el-button
        >
        <a class="workbench-preview-entry" href="?preview=workbench">进入客服平台 →</a>
      </section>
    </main>
    <AdminLayout
      v-else-if="mode === 'admin'"
      :token="staffToken"
      :role="role"
      :current-user-id="staffUser?.id || 0"
      @error="notifyError"
      @customer-session="enterEshopCustomer"
    />
    <main v-else class="chat-layout">
      <aside>
        <div class="aside-head">
          <h2>会话</h2>
          <div>
            <el-button size="small" @click="loadConversations">刷新</el-button
            ><el-button
              v-if="mode === 'customer'"
              size="small"
              type="primary"
              @click="createConversation"
              >新会话</el-button
            >
          </div>
        </div>
        <button
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conversation"
          :class="{ selected: current?.id === conversation.id }"
          @click="selectConversation(conversation)"
        >
          <strong>#{{ conversation.id }} · {{ conversation.account_name || customerAccounts.find(a => a.id === conversation.account_id)?.name || `账号 #${conversation.account_id}` }}</strong
          ><small>{{ conversationStatusLabels[conversation.status] || conversation.status }}</small
          ><span v-if="conversation.handoff_reason">{{
            conversation.handoff_reason
          }}</span>
        </button>
      </aside>
      <section class="thread">
        <div v-if="current" class="thread-head">
          <div>
            <h2>会话 #{{ current.id }}</h2>
            <small>{{ conversationStatusLabels[current.status] || current.status }}</small>
          </div>
          <div>
            <el-button
              v-if="mode === 'customer' && current.status === 'AI_ACTIVE'"
              @click="handoff"
              >转人工</el-button
            ><el-button
              v-if="mode === 'agent' && current.status === 'WAITING_USER'"
              type="primary"
              @click="claim"
              >接管</el-button
            ><el-button
              v-if="mode === 'agent' && current.status === 'HUMAN_ACTIVE'"
              @click="closeConversation"
              >结束</el-button
            >
          </div>
        </div>
        <div v-if="!current" class="empty">请选择会话，或创建新会话</div>
        <template v-else
          ><div ref="messagesContainer" class="messages">
            <article
              v-for="message in messages"
              :key="message.id"
              class="bubble"
              :class="message.sender_type.toLowerCase()"
            >
              <small
                >{{ messageSenderLabels[message.sender_type] || message.sender_type }} · {{ formatLocalDateTime(message.created_at) }}</small
              >
              <p>{{ message.content }}</p>
              <details v-if="message.citations?.length">
                <summary>知识来源</summary>
                <div
                  v-for="source in message.citations"
                  :key="source.document_id + '-' + source.version_id"
                >
                  {{ source.title }} · 文档 {{ source.document_id }} · 版本
                  {{ source.version_id }}
                </div>
              </details>
              <div
                v-if="
                  mode === 'customer' &&
                  message.sender_type === 'AI' &&
                  message.id > 0
                "
                class="feedback"
              >
                <el-button text size="small" @click="feedback(message.id, 1)"
                  >👍</el-button
                ><el-button text size="small" @click="feedback(message.id, -1)"
                  >👎</el-button
                >
              </div>
            </article>
            <div v-if="mode === 'customer' && aiTyping" class="typing-indicator" role="status" aria-live="polite">
              智能客服正在输入<span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>
            </div>
          </div>
          <div v-if="mode === 'customer' && actions.length" class="actions">
            <div v-for="action in actions" :key="action.id">
              {{ action.action }} · 订单 {{ action.order_id
              }}<el-button
                size="small"
                type="primary"
                @click="confirmAction(action.id, true)"
                >确认执行</el-button
              ><el-button size="small" @click="confirmAction(action.id, false)"
                >取消</el-button
              >
            </div>
          </div>
          <div class="composer">
            <el-input
              v-model="draft"
              type="textarea"
              :rows="2"
              :disabled="!canSend || sending"
              placeholder="输入消息"
              @keyup.ctrl.enter="send"
            /><el-button
              type="primary"
              :loading="sending"
              :disabled="!canSend || !draft.trim()"
              @click="send"
              >发送</el-button
            >
          </div></template
        >
      </section>
    </main>
    <el-dialog v-model="profileVisible" title="用户中心" width="480px">
      <el-descriptions :column="1" border><el-descriptions-item label="用户名称">{{ currentUser?.display_name || '—' }}</el-descriptions-item><el-descriptions-item label="用户名">{{ currentUser?.username || '—' }}</el-descriptions-item><el-descriptions-item label="用户类型">{{ currentTypeName }}</el-descriptions-item><el-descriptions-item label="角色">{{ currentRoleName }}</el-descriptions-item></el-descriptions>
    </el-dialog>
    <el-dialog v-model="helpVisible" title="使用帮助" width="520px">
      <p>当前身份：{{ currentTypeName }} · {{ currentRoleName }}。</p>
      <p v-if="currentUser?.user_type === 'C'">客户端可选择咨询账号、发起客服会话，并通过“我的订单”查看订单信息。</p>
      <p v-else>商户端员工可在客服工作台接待会话；管理员及有权限的员工可进入运营后台管理知识库、电商数据和系统配置。</p>
      <p>点击右上角身份菜单可查看用户信息、打开本帮助或退出登录。</p>
    </el-dialog>
    <el-drawer v-model="ordersVisible" title="我的订单（最近 50 条）" size="70%"
      ><p>
        当前用户 #{{ customerUser?.id }} · {{ customerUser?.display_name }}
      </p>
      <el-table :data="myOrders" empty-text="当前用户暂无订单；请确认下单身份"
        ><el-table-column
          prop="order_id"
          label="订单号"
          min-width="210"
        /><el-table-column prop="product_sku" label="商品" /><el-table-column
          prop="status"
          label="状态"
        /><el-table-column prop="amount" label="金额（元）" /><el-table-column
          label="操作"
          ><template #default="{ row }"
            ><el-button
              link
              @click="
                draft = row.order_id + ' 查看订单状态';
                ordersVisible = false;
              "
              >填入查询</el-button
            ></template
          ></el-table-column
        ></el-table
      ></el-drawer
    >
  </div>
</template>
<style scoped>
.typing-indicator { align-self: flex-start; padding: 12px 16px; border-radius: 12px; background: #f2f5f9; color: #5e7187; font-size: 14px; }
.typing-dots { display: inline-flex; gap: 3px; margin-left: 5px; vertical-align: middle; }
.typing-dots i { width: 4px; height: 4px; border-radius: 50%; background: currentColor; animation: typing-pulse 1.2s infinite ease-in-out; }
.typing-dots i:nth-child(2) { animation-delay: .2s; }
.typing-dots i:nth-child(3) { animation-delay: .4s; }
@keyframes typing-pulse { 0%, 60%, 100% { opacity: .3; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-3px); } }
@media (prefers-reduced-motion: reduce) { .typing-dots i { animation: none; } }
</style>
