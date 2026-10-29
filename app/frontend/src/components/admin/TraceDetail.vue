<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { vLoading } from "element-plus/es/components/loading/index.mjs";
import "element-plus/es/components/loading/style/css";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import "element-plus/es/components/message/style/css";
import { api } from "../../api";
import { routes, outcomes, locations, payloadLabels, json, time, type TraceDetail, type TraceNode } from "../../domain/traces";
const props = withDefaults(defineProps<{
  detail: TraceDetail; token?: string; embedded?: boolean;
  loadPayload?: (traceId: string, payloadId: number) => Promise<unknown>;
  tokenUsage?: { input: number | null; output: number | null };
}>(), { token: '' });
const emit = defineEmits<{ back: []; refresh: []; open: [string]; error: [unknown] }>();
const selected = ref<number | null>(props.detail.nodes[0]?.id ?? null), mode = ref("timeline"), tab = ref("nodes");
const contents = ref<Record<number, unknown>>({}), errors = ref<Record<number, string>>({}), loading = ref(false), exporting = ref(false);
const node = computed(() => props.detail.nodes.find(n => n.id === selected.value));
const graph = computed(() => props.detail.nodes.map((n, index) => {
  let depth = 0, parent = n.parent_node_id;
  while (parent && depth < 5) { depth++; parent = props.detail.nodes.find(x => x.id === parent)?.parent_node_id ?? null; }
  return { ...n, x: 40 + depth*35, y: 15+index*88 };
}));
function color(n: TraceNode) { return n.status === "FAILED" ? "var(--wb-danger, #dc2626)" : n.status === "RUNNING" ? "var(--wb-warning, #d97706)" : n.location === "remote_ai" ? "var(--wb-purple, #7c3aed)" : "var(--wb-accent, #2563eb)"; }
function edge(from: number, to: number) { const a = graph.value.find(n => n.id === from), b = graph.value.find(n => n.id === to); return a && b ? `M ${a.x+15} ${a.y+65} L ${b.x+15} ${b.y}` : ""; }
let number = 0;
async function readPayload(id: number) {
  if (props.loadPayload) return props.loadPayload(props.detail.trace_id, id);
  return (await api<{content: unknown}>(`/api/admin/question-traces/${props.detail.trace_id}/payloads/${id}`, "GET", undefined, props.token)).content;
}
watch(selected, async () => {
  const current = ++number, currentNode = node.value;
  if (!currentNode) return;
  loading.value = true;
  await Promise.all(currentNode.payloads.map(async p => {
    if (p.id in contents.value) return;
    try { contents.value[p.id] = await readPayload(p.id); delete errors.value[p.id]; }
    catch { errors.value[p.id] = "此参数快照缺失或读取失败，可重新选择节点重试。"; }
  }));
  if (current === number) loading.value = false;
}, { immediate: true });
function save(name: string, value: unknown) { const url = URL.createObjectURL(new Blob([json(value)], {type:"application/json;charset=utf-8"})); const a = document.createElement("a"); a.href=url; a.download=name; a.click(); URL.revokeObjectURL(url); }
async function copy(value: unknown) {
  const text = json(value);
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const input = document.createElement("textarea");
    input.value = text;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    const copied = document.execCommand("copy");
    input.remove();
    if (!copied) { ElMessage.error("复制失败，请手动选择内容复制"); return; }
  }
  ElMessage.success("已复制到剪贴板");
}
async function exportTrace() {
  exporting.value = true;
  try {
    const nodes = await Promise.all(props.detail.nodes.map(async n => ({...n, payloads: await Promise.all(n.payloads.map(async p => ({...p, content: await readPayload(p.id)})))})));
    save(`trace-${props.detail.trace_id}.json`, {...props.detail, nodes});
  } catch (e) { emit("error", e); } finally { exporting.value = false; }
}
</script>
<template>
  <el-card shadow="never" class="trace-detail">
    <template #header><div class="heading"><div v-if="!embedded"><el-button @click="emit('back')">返回列表</el-button> <strong>回复路由详情</strong></div><div><el-button @click="emit('refresh')">刷新详情</el-button><el-button :loading="exporting" @click="exportTrace">导出完整 JSON</el-button></div></div></template>
    <el-alert v-if="!detail.capture_complete" title="链路采集不完整" type="error" :description="detail.capture_errors.join(', ')" :closable="false" />
    <el-alert v-if="!detail.ended_at" title="本轮尚未结束；进程中断也可能留下未完成记录，不能视为执行成功。" type="warning" :closable="false" />
    <h3>{{ detail.query }}</h3>
    <el-descriptions :column="3" border>
      <el-descriptions-item label="用户">{{ detail.customer_name || detail.username }} #{{ detail.user_id }}</el-descriptions-item>
      <el-descriptions-item label="会话 / 类型">#{{ detail.conversation_id }} · {{ detail.kind }}</el-descriptions-item>
      <el-descriptions-item label="开始时间">{{ time(detail.started_at) }}</el-descriptions-item>
      <el-descriptions-item label="最终路线">{{ routes[detail.route] || detail.route }} / {{ detail.intent }}</el-descriptions-item>
      <el-descriptions-item label="处理结果">{{ outcomes[detail.outcome] || detail.outcome }} · {{ detail.status }}</el-descriptions-item>
      <el-descriptions-item label="耗时">{{ detail.latency_ms }} ms</el-descriptions-item>
      <el-descriptions-item label="AI 请求"><span v-if="!detail.ai_used">无远程 AI 调用</span><span v-for="(count, type) in detail.ai_calls" :key="type">{{ type }}：{{ count }} 次；</span></el-descriptions-item>
      <el-descriptions-item label="上下文 / 降级">{{ detail.used_context ? '使用上下文' : '未使用上下文' }} / {{ detail.fallback ? '发生降级' : '无降级' }}</el-descriptions-item>
      <el-descriptions-item label="转人工">{{ detail.handoff ? '是' : '否' }} {{ detail.handoff_reason }}</el-descriptions-item>
      <template v-if="tokenUsage">
        <el-descriptions-item label="输入 Token">{{ tokenUsage.input ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="输出 Token">{{ tokenUsage.output ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="总 Token">{{ tokenUsage.input !== null && tokenUsage.output !== null ? tokenUsage.input + tokenUsage.output : '—' }}</el-descriptions-item>
      </template>
      <el-descriptions-item label="Trace ID" :span="3"><code>{{ detail.trace_id }}</code></el-descriptions-item>
    </el-descriptions>
    <p v-if="detail.error">错误：{{ detail.error }}</p>
    <el-tabs v-model="tab">
      <el-tab-pane label="节点时序与流程" name="nodes">
        <div class="node-workspace">
          <div class="node-list">
            <el-radio-group v-model="mode"><el-radio-button value="timeline">时间线</el-radio-button><el-radio-button value="graph">流程图</el-radio-button></el-radio-group>
            <el-timeline v-if="mode === 'timeline'" class="timeline">
              <el-timeline-item v-for="n in detail.nodes" :key="n.id" :timestamp="`${time(n.started_at)} · ${n.latency_ms} ms`" :color="color(n)">
                <button class="node-button" :class="{active: selected === n.id}" @click="selected=n.id">{{ n.sequence }}. {{ n.name }}<small>{{ locations[n.location] || n.location }} · {{ n.status }}<span v-if="n.attempt > 1"> · 第 {{ n.attempt }} 次尝试</span></small></button>
              </el-timeline-item>
            </el-timeline>
            <div v-else class="flow-scroll"><svg :viewBox="`0 0 620 ${Math.max(120,graph.length*88+20)}`" role="img" aria-label="实际执行节点依赖图">
              <defs><marker id="trace-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="var(--wb-line-strong, #94a3b8)" /></marker></defs>
              <g v-for="n in graph" :key="n.id"><path v-for="up in n.depends_on" :key="up" :d="edge(up,n.id)" stroke="var(--wb-line-strong, #94a3b8)" fill="none" marker-end="url(#trace-arrow)" />
                <g tabindex="0" role="button" :aria-label="n.name" @click="selected=n.id" @keydown.enter="selected=n.id" style="cursor:pointer"><rect :x="n.x" :y="n.y" width="375" height="65" rx="8" :fill="selected===n.id?'var(--wb-accent-soft, #eff6ff)':'#fff'" :stroke="color(n)" /><text :x="n.x+12" :y="n.y+25" font-size="14">{{ n.sequence }}. {{ n.name }}</text><text :x="n.x+12" :y="n.y+48" font-size="12" fill="var(--wb-text-muted, #64748b)">{{ locations[n.location] }} · {{ n.status }} · {{ n.latency_ms }} ms</text></g>
              </g>
            </svg></div>
          </div>
          <div v-if="node" v-loading="loading" class="node-params">
            <h3>{{ node.name }}</h3><p>{{ node.node_type }} · {{ locations[node.location] }} · {{ node.status }} · {{ node.model || '无模型' }}</p>
            <p>节点 #{{ node.id }}，上级 {{ node.parent_node_id ?? '无' }}，上游 {{ node.depends_on.join(', ') || '无' }}</p>
            <p v-if="node.error" class="failure">错误：{{ node.error }}</p>
            <el-collapse><el-collapse-item title="字段来源、摘要与供应商实际用量"><pre>{{ json({sources:node.sources, summary:node.summary, usage:node.usage}) }}</pre></el-collapse-item></el-collapse>
            <el-tabs><el-tab-pane v-for="p in node.payloads" :key="p.id" :label="payloadLabels[p.kind] || p.kind">
              <p>{{ p.byte_size }} 字节 · {{ p.storage }} · 完整快照
                <el-button v-if="p.id in contents && ['input', 'output', 'raw_response'].includes(p.kind)" link type="primary" @click="copy(contents[p.id])">复制{{ payloadLabels[p.kind] || p.kind }}</el-button>
                <el-button v-if="p.id in contents" link type="primary" @click="save(`node-${node.id}-${p.kind}.json`,contents[p.id])">下载参数</el-button>
              </p>
              <el-alert v-if="errors[p.id]" :title="errors[p.id]" type="error" :closable="false" />
              <pre v-else>{{ p.id in contents ? json(contents[p.id]) : '加载中…' }}</pre>
            </el-tab-pane></el-tabs>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="上下文与参数来源" name="context"><p>以下是当时组装的上下文快照。某次 LLM 是否实际收到这些内容，请以对应节点的输入请求体为准；知识回答和分类的历史消息可能不同。</p><pre>{{ json(detail.context_sources) }}</pre></el-tab-pane>
      <el-tab-pane label="最终回复与组成" name="reply"><h3>最终保存的回复</h3><pre>{{ detail.final_reply || '本轮没有自动回复' }}</pre>
        <el-card v-for="(part,index) in detail.composition" :key="index" shadow="never"><el-tag>{{ part.kind }}</el-tag><p class="reply-part">{{ part.text }}</p><el-collapse><el-collapse-item title="输入材料与来源"><pre>{{ json(part.sources) }}</pre></el-collapse-item></el-collapse></el-card>
        <p>“已回答”表示系统给出了回复，是否解决问题仍需客户反馈；LLM 输入材料不代表可精确归因到每个生成字词。</p>
      </el-tab-pane>
      <el-tab-pane label="关联动作与操作审计" name="related">
        <p v-if="detail.parent_trace_id">来源链路：<el-button link type="primary" @click="emit('open',detail.parent_trace_id)">{{ detail.parent_trace_id }}</el-button></p>
        <p v-if="detail.pending_action_id">待确认动作 #{{ detail.pending_action_id }}</p>
        <p v-for="r in detail.related" :key="r.trace_id"><el-button link type="primary" @click="emit('open',r.trace_id)">{{ r.kind }} · {{ outcomes[r.outcome] || r.outcome }} · {{ r.trace_id }}</el-button></p>
        <el-table :data="detail.audit"><el-table-column prop="action" label="操作" /><el-table-column prop="actor" label="操作人" /><el-table-column label="时间"><template #default="{row}">{{ time(row.created_at) }}</template></el-table-column><el-table-column label="详情"><template #default="{row}">{{ json(row.detail) }}</template></el-table-column></el-table>
        <p v-if="detail.handoff">{{ detail.audit.some(a=>a.action==='claim') ? '已有客服接管，见接管审计记录。' : '尚无关联客服接管记录。' }}</p>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>
<style scoped>
.heading{display:flex;justify-content:space-between;gap:12px;align-items:center}.trace-detail{min-width:0}.node-workspace{display:grid;grid-template-columns:minmax(240px,35%) minmax(0,1fr);gap:24px}.node-list{min-width:0;max-height:850px;overflow:auto}.node-params{min-width:0}.timeline{margin-top:24px;padding-left:15px}.node-button{width:100%;text-align:left;padding:10px;border:1px solid var(--wb-line, #e2e8f0);background:white;border-radius:8px;cursor:pointer}.node-button.active{background:var(--wb-accent-soft, #eff6ff);border-color:var(--wb-accent, #2563eb)}.node-button small{display:block;margin-top:6px;color:var(--wb-text-muted, #64748b)}.flow-scroll svg{width:100%;min-width:330px}.flow-scroll{overflow:auto}pre{background:var(--wb-surface-subtle, #f6f8fc);padding:16px;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:600px;overflow:auto;font-size:12px;line-height:1.6}.failure{color:var(--wb-danger, #dc2626)}.reply-part{white-space:pre-wrap}.el-card+.el-card{margin-top:12px}@media(max-width:1100px){.node-workspace{grid-template-columns:1fr}.node-list{max-height:400px}}
</style>
