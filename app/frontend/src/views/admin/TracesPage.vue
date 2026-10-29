<script setup lang="ts">
import { ref, watch } from "vue";
import { api } from "../../api";
import type { AdminProps } from "../../domain/roles";
import { routes, outcomes, time, type TraceRow, type TraceDetail } from "../../domain/traces";
import ListPage from "../../components/admin/ListPage.vue";
import TraceDetailView from "../../components/admin/TraceDetail.vue";
const props = defineProps<AdminProps>();
const emit = defineEmits<{ error: [unknown] }>();
const rows = ref<TraceRow[]>([]), detail = ref<TraceDetail | null>(null), loading = ref(false), detailLoading = ref(false);
const page = ref(1), pageSize = ref(20), total = ref(0), dates = ref<string[]>([]);
const filters = ref({ keyword: "", conversation_id: "", route: "", outcome: "", ai_used: "", used_context: "", fallback: "", handoff: "", node_type: "" });
const aiCount = (row: TraceRow) => Object.values(row.ai_calls).reduce((a, b) => a + b, 0);
let requestNumber = 0;
async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) });
    if (props.accountId) params.set('account_id', String(props.accountId));
    for (const [key, value] of Object.entries(filters.value)) if (value) params.set(key, value);
    if (dates.value?.length === 2) { params.set("started_from", dates.value[0]!); params.set("started_to", dates.value[1]!); }
    const result = await api<{ items: TraceRow[]; total: number }>(`/api/admin/question-traces?${params}`, "GET", undefined, props.token);
    rows.value = result.items; total.value = result.total;
  } catch (e) { emit("error", e); } finally { loading.value = false; }
}
function query() { if (page.value === 1) void load(); else page.value = 1; }
function reset() { for (const key of Object.keys(filters.value) as (keyof typeof filters.value)[]) filters.value[key] = ""; dates.value = []; query(); }
async function open(traceId: string) {
  const number = ++requestNumber; detailLoading.value = true;
  try { const result = await api<TraceDetail>(`/api/admin/question-traces/${traceId}`, "GET", undefined, props.token); if (number === requestNumber) detail.value = result; }
  catch (e) { emit("error", e); } finally { if (number === requestNumber) detailLoading.value = false; }
}
watch([page, pageSize, () => props.accountId], load, { immediate: true });
</script>
<template>
  <div v-loading="detailLoading">
    <TraceDetailView v-if="detail" :key="detail.trace_id" :detail="detail" :token="props.token"
      @back="detail = null; load()" @open="open" @refresh="open(detail.trace_id)" @error="emit('error', $event)" />
    <ListPage v-else title="回复路由记录"
      description="列表显示用户问题、智能客服回复与处理结果；点击详情可查看实际执行节点、AI 调用和上下文。"
      :loading="loading" :total="total" v-model:page="page" v-model:page-size="pageSize">
      <template #filters>
        <el-input v-model="filters.keyword" placeholder="问题 / 用户名 / Trace ID" clearable @keyup.enter="query" />
        <el-input v-model="filters.conversation_id" placeholder="会话 ID" clearable />
        <el-date-picker v-model="dates" type="datetimerange" start-placeholder="开始时间" end-placeholder="结束时间" value-format="YYYY-MM-DDTHH:mm:ssZ" />
        <el-select v-model="filters.route" placeholder="处理路线" clearable><el-option v-for="(label, value) in routes" :key="value" :label="label" :value="value" /></el-select>
        <el-select v-model="filters.outcome" placeholder="处理结果" clearable><el-option v-for="(label, value) in outcomes" :key="value" :label="label" :value="value" /></el-select>
        <el-select v-for="(label, key) in {ai_used:'调用远程 AI', used_context:'使用上下文', fallback:'发生降级', handoff:'转人工'}" :key="key" v-model="filters[key]" :placeholder="label" clearable>
          <el-option :label="`${label}：是`" value="true" /><el-option :label="`${label}：否`" value="false" />
        </el-select>
        <el-select v-model="filters.node_type" placeholder="经过节点" clearable>
          <el-option v-for="(label, value) in {'llm.route':'LLM 分类', 'llm.generate':'LLM 回复', 'ai.embed':'Embedding', 'ai.rerank':'Rerank', 'search.bm25':'OpenSearch BM25', 'search.vector':'OpenSearch 向量', 'business.tool':'业务工具', 'local.fallback':'降级'}" :key="value" :value="value" :label="label" />
        </el-select>
        <el-button type="primary" @click="query">查询</el-button><el-button @click="reset">重置</el-button>
      </template>
      <el-table :data="rows" stripe border class="trace-table" table-layout="fixed">
        <el-table-column label="时间 / 会话" width="130"><template #default="{row}">{{ time(row.started_at) }}<br />会话 #{{ row.conversation_id }}</template></el-table-column>
        <el-table-column label="用户" width="105"><template #default="{row}">{{ row.customer_name || row.username }}<br />#{{ row.user_id }}</template></el-table-column>
        <el-table-column label="用户问题 / 智能客服回复" min-width="250"><template #default="{row}">
          <div class="trace-question">{{ row.query }}</div>
          <div class="trace-reply" tabindex="0"><span class="trace-reply-label">智能客服：</span>{{ row.final_reply || '本轮暂无自动回复' }}</div>
        </template></el-table-column>
        <el-table-column label="AI / 上下文" width="120"><template #default="{row}">AI 请求 {{ aiCount(row) }} 次<br />上下文：{{ row.used_context ? '使用' : '未使用' }}</template></el-table-column>
        <el-table-column label="结果" width="145"><template #default="{row}">{{ outcomes[row.outcome] || row.outcome }}<br /><el-tag v-if="row.fallback" type="warning" size="small">降级</el-tag> <el-tag v-if="row.handoff" type="warning" size="small">转人工</el-tag><el-tag v-if="!row.capture_complete" type="danger" size="small">采集不完整</el-tag></template></el-table-column>
        <el-table-column prop="latency_ms" label="耗时 ms" width="80" />
        <el-table-column label="操作" width="70"><template #default="{row}"><el-button link type="primary" @click="open(row.trace_id)">详情</el-button></template></el-table-column>
      </el-table>
    </ListPage>
  </div>
</template>
<style scoped>
.trace-question{white-space:pre-wrap;overflow-wrap:anywhere;font-weight:600}
.trace-reply{max-height:92px;overflow-y:auto;overflow-x:hidden;margin-top:8px;padding:8px 10px;border-radius:6px;background:#f5f8fc;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5}
.trace-reply-label{color:#64748b;font-weight:600}
.trace-table :deep(.cell){overflow-wrap:anywhere;line-height:1.5}
</style>
