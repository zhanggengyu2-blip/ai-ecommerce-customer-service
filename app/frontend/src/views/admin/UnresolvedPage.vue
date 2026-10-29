<script setup lang="ts">
import { ref, watch } from "vue";
import { api } from "../../api";
import ListPage from "../../components/admin/ListPage.vue";
import { formatLocalDateTime } from "../../domain/datetime";
import { conversationStatusLabels } from "../../domain/conversationLabels";
import type { AdminProps } from "../../domain/roles";

type UnresolvedQuestion = {
  trace_id: string;
  conversation_id: number;
  customer_name: string;
  query: string;
  final_reply: string;
  started_at: string;
  reason: string;
  conversation_status: string;
};
const props = defineProps<AdminProps>();
const emit = defineEmits<{ error: [unknown] }>();
const rows = ref<UnresolvedQuestion[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) });
    if (props.accountId) params.set("account_id", String(props.accountId));
    if (keyword.value.trim()) params.set("keyword", keyword.value.trim());
    const result = await api<{ items: UnresolvedQuestion[]; total: number }>(
      `/api/admin/unresolved-questions?${params}`, "GET", undefined, props.token);
    rows.value = result.items;
    total.value = result.total;
  } catch (error) {
    emit("error", error);
  } finally {
    loading.value = false;
  }
}
function query() { if (page.value === 1) void load(); else page.value = 1; }
function reset() { keyword.value = ""; query(); }
watch([page, pageSize, () => props.accountId], load, { immediate: true });
</script>

<template>
  <ListPage title="未解决问题" :loading="loading" :total="total"
    description="待跟进线索：客户对回答点差评，或当前会话的最新提问仍待补充信息、等待人工接管。已由人工接管或结束的会话不再因历史转人工记录入列；差评需人工核实是否已解决。"
    v-model:page="page" v-model:page-size="pageSize">
    <template #filters>
      <el-input v-model="keyword" clearable placeholder="搜索问题或用户" @keyup.enter="query" />
      <el-button type="primary" @click="query">查询</el-button>
      <el-button @click="reset">重置</el-button>
    </template>
    <el-table :data="rows" stripe border empty-text="暂无待跟进问题">
      <el-table-column label="提问时间" width="175"><template #default="{ row }">{{ formatLocalDateTime(row.started_at) }}</template></el-table-column>
      <el-table-column prop="customer_name" label="客户" width="160" show-overflow-tooltip />
      <el-table-column label="会话" width="100"><template #default="{ row }">#{{ row.conversation_id }}</template></el-table-column>
      <el-table-column prop="query" label="客户问题" min-width="240" show-overflow-tooltip />
      <el-table-column prop="final_reply" label="当前回复" min-width="260" show-overflow-tooltip />
      <el-table-column prop="reason" label="待跟进原因" width="170" />
      <el-table-column label="会话状态" width="165"><template #default="{ row }">{{ conversationStatusLabels[row.conversation_status] || row.conversation_status }}</template></el-table-column>
    </el-table>
  </ListPage>
</template>
