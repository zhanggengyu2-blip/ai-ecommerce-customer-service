<script setup lang="ts">
import { computed, ref } from 'vue';
import { usePreview } from '../usePreviewStore';
import { dateOf, statusLabels, type WorkbenchOrder } from '../../workbench/types';
import MessageTimeline from '../../workbench/components/MessageTimeline.vue';
import OrderDetailDialog from '../../workbench/components/OrderDetailDialog.vue';
const s = usePreview();
const open = computed({ get: () => s.recordId.value !== null, set: value => { if (!value) s.recordId.value = null; } });
const record = computed(() => {
  const c = s.wb.conversations.value.find(c => c.id === s.recordId.value);
  if (c) return { id: c.id, customer: c.customer, agent: c.agent || 'AI 客服', status: statusLabels[c.status],
    endedAt: c.status === 'CLOSED' ? c.lastMessageAt : '', messages: c.messages, orders: c.orders };
  const h = s.histories.value.find(h => h.id === s.recordId.value);
  return h ? { ...h, status: '已完结' } : null;
});
const traces = computed(() => s.traces.value.filter(t => t.conversationId === s.recordId.value));
const total = computed(() => !traces.value.length || traces.value.some(t => t.input === null || t.output === null)
  ? '—' : traces.value.reduce((n,t) => n+t.input!+t.output!,0).toLocaleString());
const order = ref<WorkbenchOrder | null>(null), orderOpen = ref(false), imageOpen = ref(false), imageUrl = ref('');
</script>
<template>
  <el-drawer v-model="open" :title="`${record?.customer || ''} · 会话 #${s.recordId.value || ''}`"
    size="min(780px, 100vw)" class="wb-history-drawer pv-history" append-to-body>
    <div v-if="record" class="pv-history-body">
      <div class="pv-detail-strip"><span>接待人：{{record.agent}}</span><span>{{record.status}}</span>
        <span v-if="record.endedAt">完结于 {{dateOf(record.endedAt)}}</span><span>总 Token：{{total}}</span></div>
      <MessageTimeline :key="record.id" :messages="record.messages" :orders="record.orders" :customer="record.customer" history
        @order="order=$event;orderOpen=true" @image="imageUrl=$event;imageOpen=true"/>
      <section v-if="traces.length" class="pv-trace-links"><h3>本次 AI 回复记录</h3>
        <button v-for="t in traces" :key="t.id" @click="s.openTrace(t.id)"><span>{{t.question}}</span><span>查看回复路由 →</span></button>
      </section>
    </div>
    <div v-else class="pv-empty"><strong>未找到该会话记录</strong></div>
  </el-drawer>
  <OrderDetailDialog v-model="orderOpen" :order="order"/>
  <el-dialog v-model="imageOpen" title="会话图片" width="min(760px, 92vw)" class="wb-dialog wb-image-dialog" align-center append-to-body>
    <img :src="imageUrl" alt="会话图片大图"/>
  </el-dialog>
</template>
