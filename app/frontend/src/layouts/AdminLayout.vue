<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch, type Component } from "vue";
import * as Icons from "@element-plus/icons-vue";
import { adminMenus } from "./adminMenus";
import { api } from "../api";
const props = defineProps<{
  token: string;
  role: string;
  currentUserId: number;
}>();
const emit = defineEmits<{
  error: [unknown];
  customerSession: [string, string, number];
}>();
const menus = computed(() => adminMenus(props.role));
const menuIcons: Record<string, Component> = {
  HomeFilled: Icons.HomeFilled, Service: Icons.Service, ShoppingCart: Icons.ShoppingCart,
  Reading: Icons.Reading, Cpu: Icons.Cpu, DataAnalysis: Icons.DataAnalysis, Setting: Icons.Setting,
  Odometer: Icons.Odometer, ChatDotRound: Icons.ChatDotRound, Clock: Icons.Clock,
  ChatLineRound: Icons.ChatLineRound, Switch: Icons.Switch, User: Icons.User,
  Goods: Icons.Goods, Tickets: Icons.Tickets, Money: Icons.Money, Van: Icons.Van,
  Refresh: Icons.Refresh, Coin: Icons.Coin, Collection: Icons.Collection,
  Document: Icons.Document, EditPen: Icons.EditPen, Connection: Icons.Connection,
  Search: Icons.Search, TrendCharts: Icons.TrendCharts, ChatSquare: Icons.ChatSquare,
  Warning: Icons.Warning, Key: Icons.Key, Link: Icons.Link,
};
type Account = { id: number; name: string; platform_name: string; platform_code: string; commerce_enabled: boolean };
const accounts = ref<Account[]>([]);
const accountId = ref<number | null>(Number(localStorage.getItem('adminAccountId')) || null);
async function loadAccounts() {
  try { accounts.value = await api<Account[]>('/api/admin/accounts', 'GET', undefined, props.token); }
  catch (error) { emit('error', error); }
}
onMounted(loadAccounts);
watch(accountId, value => localStorage.setItem('adminAccountId', value ? String(value) : ''));
const eshopAccountId = computed(() => accountId.value && accounts.value.find(a => a.id === accountId.value && a.commerce_enabled)
  ? accountId.value : accounts.value.find(a => a.platform_code === 'PINDUODUO')?.id || accounts.value.find(a => a.commerce_enabled)?.id || 1);
const savedPage = localStorage.getItem("adminPage") || "dashboard";
const page = ref(["versions", "parsing"].includes(savedPage) ? "documents" : savedPage),
  refreshKey = ref(0);
watch([page, accounts], () => {
  if (page.value.startsWith('eshop-') && (!accountId.value || !accounts.value.some(a => a.id === accountId.value && a.commerce_enabled)))
    accountId.value = eshopAccountId.value;
}, { immediate: true });
const activeGroup = computed(() =>
  menus.value.find((group) =>
    group.items.some((item) => item.key === page.value),
  ),
);
const title = computed(
  () =>
    activeGroup.value?.items.find((item) => item.key === page.value)?.label ||
    "",
);
watch(
  menus,
  (groups) => {
    if (
      !groups.some((group) =>
        group.items.some((item) => item.key === page.value),
      )
    )
      page.value = groups[0]?.items[0]?.key || "support-live";
  },
  { immediate: true },
);
watch(page, (value) => localStorage.setItem("adminPage", value));
const pages = {
  users: defineAsyncComponent(() => import("../views/admin/UsersPage.vue")),
  accounts: defineAsyncComponent(() => import("../views/admin/AccountsPage.vue")),
  dashboard: defineAsyncComponent(
    () => import("../views/admin/DashboardPage.vue"),
  ),
  knowledge: defineAsyncComponent(
    () => import("../views/admin/KnowledgePage.vue"),
  ),
  documents: defineAsyncComponent(
    () => import("../views/admin/DocumentsPage.vue"),
  ),
  configs: defineAsyncComponent(() => import("../views/admin/ConfigsPage.vue")),
  records: defineAsyncComponent(() => import("../views/admin/RecordsPage.vue")),
  traces: defineAsyncComponent(() => import("../views/admin/TracesPage.vue")),
  unresolved: defineAsyncComponent(() => import("../views/admin/UnresolvedPage.vue")),
  services: defineAsyncComponent(
    () => import("../views/admin/ServicesPage.vue"),
  ),
  roles: defineAsyncComponent(() => import("../views/admin/RolesPage.vue")),
  eshop: defineAsyncComponent(() => import("../EshopPanel.vue")),
  support: defineAsyncComponent(() => import("../AdminConversations.vue")),
};
const currentPage = computed(
  () =>
    pages[
      page.value.startsWith("eshop-")
        ? "eshop"
        : page.value.startsWith("support-")
          ? "support"
          : page.value.startsWith("config-")
            ? "configs"
            : page.value === "documents"
              ? "documents"
              : page.value === "executions"
                ? "traces"
              : [
                    "audit",
                    "feedback",
                    "popular",
                  ].includes(page.value)
                ? "records"
                : ["api", "embedding"].includes(page.value)
                  ? "services"
                  : page.value === "metrics"
                    ? "dashboard"
                    : (page.value as keyof typeof pages)
    ],
);
const view = computed(() =>
  page.value.startsWith("eshop-")
    ? page.value.slice(6)
    : page.value.startsWith("support-")
      ? page.value.slice(8)
      : page.value,
);
const readonly = computed(() =>
  page.value.startsWith("support-")
    ? !["SUPER_ADMIN", "ADMIN", "CUSTOMER_SERVICE"].includes(props.role)
    : !["SUPER_ADMIN", "ADMIN"].includes(props.role),
);
const pageProps = computed(() =>
  page.value.startsWith("eshop-") || page.value.startsWith("support-")
    ? { token: props.token, view: view.value, readonly: readonly.value,
        accountId: page.value.startsWith('eshop-') ? eshopAccountId.value : accountId.value }
    : page.value === "roles"
      ? {}
      : {
          token: props.token,
          role: props.role,
          currentUserId: props.currentUserId,
          accountId: accountId.value,
          page: page.value,
        },
);
const pageEvents = computed(() => ({
  ...(page.value !== "roles" ? { error: (error: unknown) => emit("error", error) } : {}),
  ...(page.value.startsWith("eshop-")
    ? { customerSession: (token: string, name: string, accountId: number) => emit("customerSession", token, name, accountId) }
    : {}),
  ...(["knowledge"].includes(page.value)
    ? { navigate: (next: string) => { page.value = next; } }
    : {}),
  ...(page.value === "accounts" ? { accountsChanged: loadAccounts } : {}),
}));
</script>

<template>
  <main class="admin-workspace">
    <aside class="admin-nav">
      <el-menu
        :default-active="page"
        :default-openeds="[activeGroup?.title || '总览']"
        unique-opened
        background-color="#142337"
        text-color="#d8e1ed"
        active-text-color="#fff"
        @select="page = $event"
      >
        <el-sub-menu
          v-for="group in menus"
          :key="group.title"
          :index="group.title"
          ><template #title><el-icon><component :is="menuIcons[group.icon]" /></el-icon><span>{{ group.title }}</span></template
          ><el-menu-item
            v-for="item in group.items"
            :key="item.key"
            :index="item.key"
            ><el-icon><component :is="menuIcons[item.icon]" /></el-icon><span>{{ item.label }}</span></el-menu-item
          ></el-sub-menu
        >
      </el-menu>
    </aside>
    <div class="admin-content">
      <div class="admin-toolbar">
        <div>
          <el-breadcrumb separator="/"
            ><el-breadcrumb-item>运营后台</el-breadcrumb-item
            ><el-breadcrumb-item>{{ activeGroup?.title }}</el-breadcrumb-item
            ><el-breadcrumb-item>{{ title }}</el-breadcrumb-item></el-breadcrumb
          >
        </div>
        <div class="row">
          <el-select v-model="accountId" placeholder="全部账号" clearable style="width: 220px">
            <el-option v-for="account in accounts" :key="account.id"
              :label="`${account.platform_name} · ${account.name}`" :value="account.id" />
          </el-select>
          <el-button @click="refreshKey++">刷新数据</el-button>
        </div>
      </div>
      <Suspense
        ><component
          :is="currentPage"
          :key="`${page}:${refreshKey}`"
          v-bind="pageProps"
          v-on="pageEvents" /><template #fallback
          ><el-skeleton :rows="6" animated /></template
      ></Suspense>
    </div>
  </main>
</template>
