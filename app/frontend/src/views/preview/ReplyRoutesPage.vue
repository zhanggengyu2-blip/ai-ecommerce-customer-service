<script setup lang="ts">
import PreviewDatePicker from '../../features/preview/components/PreviewDatePicker.vue';
import { computed, reactive, ref } from 'vue';
import { usePreview } from '../../features/preview/usePreviewStore';
import { replyTrace } from '../../features/preview/replyTraces';
import { routes, outcomes, time } from '../../domain/traces';
import PageHeading from '../../features/preview/components/PageHeading.vue';
import TableFooter from '../../features/preview/components/TableFooter.vue';
const s=usePreview(), page=ref(1), advanced=ref(false);
const empty=()=>({keyword:'',conversation_id:'',from:'',to:'',route:'',outcome:'',ai_used:'',used_context:'',fallback:'',handoff:'',node_type:''});
const filters=reactive(empty()), applied=ref(empty());
const nodes={'llm.route':'LLM 分类','llm.generate':'LLM 回复','ai.embed':'Embedding（向量化）','ai.rerank':'Rerank（重排序）','search.bm25':'关键词检索','search.vector':'向量检索','business.tool':'业务工具','local.fallback':'降级'};
const rows=computed(()=>s.traces.value.map(t=>({...t, detail:replyTrace(t).detail})).filter(t=>{
  const d=t.detail, f=applied.value;
  return (!f.keyword||`${d.query} ${d.final_reply} ${d.customer_name} ${d.trace_id}`.includes(f.keyword.trim()))
    &&(!f.conversation_id||String(d.conversation_id)===f.conversation_id.trim())
    &&(!f.from||Date.parse(d.started_at)>=Date.parse(f.from))
    &&(!f.to||Date.parse(d.started_at)<=Date.parse(f.to))
    &&(!f.route||d.route===f.route)&&(!f.outcome||d.outcome===f.outcome)
    &&(['ai_used','used_context','fallback','handoff'] as const).every(key=>!f[key]||String(d[key])===f[key])
    &&(!f.node_type||d.nodes.some(n=>n.node_type===f.node_type));
}));
function query(){applied.value={...filters};page.value=1;}
function reset(){Object.assign(filters,empty());query();}
const initial=Number(new URLSearchParams(window.location.hash.split('?')[1]).get('id'));
if(initial)s.openTrace(initial);
</script>
<template><div class="pv-page"><PageHeading title="回复路由记录" description="查看客户问题、AI 回复和处理结果；展开详情可查看执行节点、参数快照及上下文。"/>
  <div class="pv-card">
    <form class="pv-route-filters" @submit.prevent="query">
      <div class="pv-route-main-filters">
        <el-input v-model="filters.keyword" placeholder="问题 / 客户 / Trace ID" aria-label="搜索回复路由" clearable/>
        <el-input v-model="filters.conversation_id" placeholder="会话 ID" aria-label="会话 ID" clearable/>
        <el-select v-model="filters.route" placeholder="处理路线" aria-label="处理路线" clearable><el-option v-for="(label,value) in routes" :key="value" :label="label" :value="value"/></el-select>
        <el-select v-model="filters.outcome" placeholder="处理结果" aria-label="处理结果" clearable><el-option v-for="(label,value) in outcomes" :key="value" :label="label" :value="value"/></el-select>
        <button class="wb-btn primary" type="submit">查询</button><button class="wb-btn" type="button" @click="reset">重置</button>
        <button class="wb-text-button" type="button" :aria-expanded="advanced" @click="advanced=!advanced">{{advanced?'收起筛选':'更多筛选'}}</button>
      </div>
      <div v-if="advanced" class="pv-route-extra-filters">
        <label>开始时间<PreviewDatePicker v-model="filters.from" type="datetime" aria-label="开始时间"/></label>
        <label>结束时间<PreviewDatePicker v-model="filters.to" type="datetime" :min="filters.from||undefined" aria-label="结束时间"/></label>
        <el-select v-for="(label,key) in {ai_used:'调用远程 AI',used_context:'使用上下文',fallback:'发生降级',handoff:'转人工'}" :key="key" v-model="filters[key]" :placeholder="label" :aria-label="label" clearable>
          <el-option :label="`${label}：是`" value="true"/><el-option :label="`${label}：否`" value="false"/>
        </el-select>
        <el-select v-model="filters.node_type" placeholder="经过节点" aria-label="经过节点" clearable><el-option v-for="(label,value) in nodes" :key="value" :label="label" :value="value"/></el-select>
      </div>
    </form>
    <div class="pv-table-scroll"><table class="pv-table pv-routes-table"><colgroup><col style="width:150px"/><col style="width:90px"/><col/><col style="width:160px"/><col style="width:180px"/><col style="width:150px"/><col style="width:100px"/><col style="width:100px"/><col style="width:76px"/></colgroup><thead><tr>
      <th>时间 / 会话</th><th>客户</th><th>客户问题 / AI 回复</th><th>AI / 上下文</th><th>处理结果</th><th>输入 / 输出 Token</th><th>总 Token</th><th>耗时</th><th>操作</th>
    </tr></thead><tbody><tr v-for="t in rows.slice((page-1)*20,page*20)" :key="t.id">
      <td>{{time(t.createdAt)}}<small>会话 #{{t.conversationId}}</small></td><td>{{t.customer}}</td>
      <td class="pv-route-message"><strong>{{t.question}}</strong><p tabindex="0">{{t.answer}}</p></td>
      <td><div class="pv-route-meta"><div><span>AI 请求</span><strong>{{t.detail.capture_complete?`${Object.values(t.detail.ai_calls).reduce((a,b)=>a+b,0)} 次`:'—'}}</strong></div><div><span>上下文</span><strong>{{t.detail.used_context?'已使用':'未使用'}}</strong></div></div></td>
      <td><div class="pv-route-result"><strong>{{t.detail.outcome==='ANSWERED'?'已回答':outcomes[t.detail.outcome]||t.detail.outcome}}</strong><small v-if="t.detail.outcome==='ANSWERED'">待客户反馈</small><div class="pv-route-result-tags"><span class="pv-tag">{{routes[t.detail.route]||t.detail.route}}</span><span v-if="!t.detail.capture_complete" class="pv-tag amber">采集不完整</span></div></div></td>
      <td>{{t.input??'—'}} / {{t.output??'—'}}</td><td>{{t.input!==null&&t.output!==null?t.input+t.output:'—'}}</td>
      <td>{{t.detail.capture_complete?`${t.detail.latency_ms} ms`:'—'}}</td>
      <td><button class="wb-text-button" @click="s.openTrace(t.id)">详情</button></td>
    </tr><tr v-if="!rows.length"><td colspan="9"><div class="pv-empty"><strong>没有符合条件的回复路由</strong></div></td></tr></tbody></table></div>
    <TableFooter v-model:page="page" :total="rows.length" :size="20"/>
  </div>
</div></template>
