<script setup lang="ts">
import PreviewDatePicker from '../../features/preview/components/PreviewDatePicker.vue';
import PreviewSelect from '../../features/preview/components/PreviewSelect.vue';
import { computed, ref, watch } from 'vue';
import { usePreview, type HistoryRow } from '../../features/preview/usePreviewStore';
import { dateOf } from '../../features/workbench/types';
import PageHeading from '../../features/preview/components/PageHeading.vue';
import TableFooter from '../../features/preview/components/TableFooter.vue';
import Icon from '../../features/workbench/components/WorkbenchIcon.vue';
const s=usePreview(), search=ref(''), agent=ref(''), date=ref(''),page=ref(1);
const rows=computed(()=>s.histories.value.filter(h=>`${h.customer} ${h.id} ${h.summary}`.includes(search.value.trim())&&(!agent.value||h.agent===agent.value)&&(!date.value||h.endedAt.slice(0,10)===date.value)));
watch([search,agent,date],()=>page.value=1);
function show(h: HistoryRow){s.openRecord(h.id);}
function total(id: number){const ts=s.traces.value.filter(t=>t.conversationId===id);return !ts.length||ts.some(t=>t.input===null||t.output===null)?'—':ts.reduce((sum,t)=>sum+t.input!+t.output!,0).toLocaleString();}
const initial=Number(new URLSearchParams(window.location.hash.split('?')[1]).get('id')); if(initial){const h=s.histories.value.find(h=>h.id===initial);if(h)show(h);}
</script>
<template><div class="pv-page"><PageHeading title="历史会话记录" description="查看全店已完结的 AI 与人工会话，保留完整沟通内容。" eyebrow="客服中心"/><div class="pv-card"><div class="pv-filters"><div class="pv-search"><Icon name="Search"/><input v-model="search" placeholder="搜索客户、会话或内容" aria-label="搜索历史会话"/></div><PreviewSelect v-model="agent" aria-label="接待人筛选"><option value="">全部接待人</option><option>AI 客服</option><option>客服小林</option><option>客服小周</option></PreviewSelect><PreviewDatePicker v-model="date" type="date" aria-label="完结日期"/><button v-if="search||agent||date" class="wb-text-button" @click="search='';agent='';date=''">重置</button></div><div class="pv-table-scroll"><table class="pv-table"><thead><tr><th>客户</th><th>会话 ID</th><th>主要咨询内容</th><th>接待人</th><th>完结时间</th><th>总 Token</th><th>操作</th></tr></thead><tbody><tr v-for="h in rows.slice((page-1)*8,page*8)" :key="h.id"><td><div class="pv-customer"><span class="wb-avatar blue">{{h.customer[0]}}</span><div><strong>{{h.customer}}</strong></div></div></td><td>#{{h.id}}</td><td class="pv-wide-cell">{{h.summary}}</td><td><span class="pv-tag" :class="h.human?'green':'blue'">{{h.agent}}</span></td><td>{{dateOf(h.endedAt)}}</td><td class="pv-number">{{total(h.id)}}</td><td><button class="wb-text-button" @click="show(h)">查看完整会话</button></td></tr><tr v-if="!rows.length"><td colspan="7"><div class="pv-empty"><Icon name="Document"/><strong>没有符合条件的历史会话</strong><span>试试其他客户或日期</span></div></td></tr></tbody></table></div><TableFooter v-model:page="page" :total="rows.length"/></div>
</div></template>
