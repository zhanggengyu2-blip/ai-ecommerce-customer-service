<script setup lang="ts">
import PreviewSelect from '../../features/preview/components/PreviewSelect.vue';
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import { usePreview, navigate } from '../../features/preview/usePreviewStore';
import { dateOf, ticketTypeLabels, statusLabels } from '../../features/workbench/types';
import type { WorkbenchConversation, WorkbenchOrder, WorkbenchTicket } from '../../features/workbench/types';
import TicketDialog from '../../features/workbench/components/TicketDialog.vue';
import PageHeading from '../../features/preview/components/PageHeading.vue';
import TableFooter from '../../features/preview/components/TableFooter.vue';
import Icon from '../../features/workbench/components/WorkbenchIcon.vue';
const s = usePreview(), { conversations } = s.wb;
const tab = ref('PENDING'), search = ref(''), type = ref(''), page = ref(1);
const rows = computed(() => s.tickets.value.filter(t => t.completion === tab.value && (!type.value || t.types.includes(type.value as never)) && `${t.number} ${t.description} ${conversation(t.conversationId)?.customer} ${order(t)?.number}`.includes(search.value.trim())).sort((a,b) => Date.parse(b.createdAt)-Date.parse(a.createdAt)));
watch([tab,search,type],()=>page.value=1);
const pick = ref(false), selectedConversation = ref<number | ''>(''), selectedOrder = ref<number | ''>('');
const pickConversation = computed(() => conversations.value.find(c => c.id === selectedConversation.value) || null);
watch(selectedConversation,()=>selectedOrder.value='');
const open = ref(false), editing = ref<WorkbenchTicket|null>(null), context = ref<WorkbenchConversation|null>(null), ticketOrder = ref<WorkbenchOrder|null>(null), busy = ref<number|null>(null);
function conversation(id: number) { return conversations.value.find(c=>c.id===id); }
function order(t: WorkbenchTicket) { return conversation(t.conversationId)?.orders.find(o=>o.id===t.orderId); }
function edit(t: WorkbenchTicket) { editing.value=t; context.value=conversation(t.conversationId)||null; ticketOrder.value=order(t)||null; open.value=true; }
function create() { if (!pickConversation.value) return; const o=pickConversation.value.orders.find(o=>o.id===selectedOrder.value); if(!o)return; const existing=pickConversation.value.tickets.find(t=>t.orderId===o.id); context.value=pickConversation.value; ticketOrder.value=o; editing.value=existing||null; pick.value=false; open.value=true; }
async function complete(t: WorkbenchTicket) { if(busy.value)return; busy.value=t.id; try{await s.wb.completeTicket(t.id);ElMessage.success('已标记完成，订单与会话不受影响');}catch(e){ElMessage.error((e as Error).message);}finally{busy.value=null;} }
function go(t: WorkbenchTicket){s.openRecord(t.conversationId);}
</script>
<template><div class="pv-page"><PageHeading title="待办事项" description="全店的售后诉求集中在这里，处理后手动标记完成。" eyebrow="客服中心"/>
  <div class="pv-card"><div class="pv-tabs" role="tablist"><button v-for="item in [{id:'PENDING',label:'待完成'},{id:'DONE',label:'已完成'}]" :key="item.id" role="tab" :aria-selected="tab===item.id" :class="{active:tab===item.id}" @click="tab=item.id">{{item.label}}<span>{{s.tickets.value.filter(t=>t.completion===item.id).length}}</span></button></div>
    <div class="pv-filters"><div class="pv-search"><Icon name="Search"/><input v-model="search" aria-label="搜索工单" placeholder="搜索工单、客户或订单"/></div><PreviewSelect v-model="type" aria-label="诉求类型筛选"><option value="">全部诉求类型</option><option v-for="(label,key) in ticketTypeLabels" :key="key" :value="key">{{label}}</option></PreviewSelect><div class="pv-card-actions pv-filter-end"><button class="wb-btn primary" @click="pick=true;selectedConversation='';selectedOrder='' "><Icon name="Plus"/>新增工单</button></div></div>
    <div class="pv-table-scroll"><table class="pv-table"><thead><tr><th>工单 / 创建时间</th><th>客户与订单</th><th>售后诉求</th><th>{{tab==='DONE'?'完成信息':'来源'}}</th><th class="pv-action-col">操作</th></tr></thead><tbody><tr v-for="t in rows.slice((page-1)*8,page*8)" :key="t.id"><td><strong>{{t.number}}</strong><small>{{dateOf(t.createdAt)}}</small></td><td>{{conversation(t.conversationId)?.customer}}<small>{{order(t)?.number}}</small></td><td class="pv-wide-cell"><div class="pv-tags"><span v-for="kind in t.types" :key="kind" class="pv-tag blue">{{ticketTypeLabels[kind]}}</span></div><p class="pv-cell-summary">{{t.description}}</p></td><td><template v-if="t.completion==='DONE'">{{t.completedBy}}<small>{{t.completedAt?dateOf(t.completedAt):'—'}}</small></template><span v-else class="pv-tag" :class="t.source==='AI'?'purple':''">{{t.source==='AI'?'AI 创建':'客服创建'}}</span></td><td><div class="pv-row-actions"><button @click="edit(t)">查看 / 编辑</button><button @click="go(t)">会话记录</button><button v-if="tab==='PENDING'" :disabled="busy===t.id" @click="complete(t)">标记完成</button></div></td></tr><tr v-if="!rows.length"><td colspan="5"><div class="pv-empty"><Icon name="CircleCheck"/><strong>{{search||type?'没有符合条件的工单':tab==='DONE'?'还没有已完成的工单':'当前没有待完成工单'}}</strong><span>会话中创建的客服工单也会同步显示在这里</span></div></td></tr></tbody></table></div><TableFooter v-model:page="page" :total="rows.length"/></div>
  <el-dialog v-model="pick" title="选择关联会话和订单" width="520px" class="wb-dialog" align-center><div class="pv-form"><p class="pv-muted">先选择会话，再选择这次会话内的订单。</p><label>关联会话<PreviewSelect v-model="selectedConversation" aria-label="关联会话"><option value="">请选择会话</option><option v-for="c in conversations.filter(c=>c.orders.length)" :key="c.id" :value="c.id">{{c.customer}} · 会话 #{{c.id}} （{{c.status==='HUMAN_ACTIVE'?'人工接待中':c.status==='AI_ACTIVE'?'AI 接待中':statusLabels[c.status]}}）</option></PreviewSelect></label><label>客户<input :value="pickConversation?.customer||'随会话自动确定'" readonly/></label><label>关联订单<PreviewSelect v-model="selectedOrder" :disabled="!pickConversation" aria-label="关联订单"><option value="">请选择订单</option><option v-for="o in pickConversation?.orders" :key="o.id" :value="o.id">{{o.number}} · {{o.product}}</option></PreviewSelect></label></div><template #footer><button class="wb-btn" @click="pick=false">取消</button><button class="wb-btn primary" :disabled="!selectedOrder" @click="create">下一步</button></template></el-dialog>
  <TicketDialog v-model="open" :conversation="context" :order="ticketOrder" :ticket="editing" :save="s.wb.saveTicket" @saved="ElMessage.success('工单已保存')"/>
</div></template>
