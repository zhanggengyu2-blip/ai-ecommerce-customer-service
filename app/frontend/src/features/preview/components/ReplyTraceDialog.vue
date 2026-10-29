<script setup lang="ts">
import { computed, ref } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import TraceDetailView from '../../../components/admin/TraceDetail.vue';
import { usePreview } from '../usePreviewStore';
import { replyTrace } from '../replyTraces';
const s = usePreview(), revision = ref(0);
const open = computed({ get: () => s.traceId.value !== null, set: v => { if (!v) s.traceId.value = null; } });
const trace = computed(() => s.traces.value.find(t => t.id === s.traceId.value));
const snapshot = computed(() => trace.value ? replyTrace(trace.value) : null);
async function loadPayload(_traceId: string, id: number) {
  if (!snapshot.value || !(id in snapshot.value.payloads)) throw new Error('未找到参数快照');
  return snapshot.value.payloads[id];
}
function related(id: string) {
  const found = s.traces.value.find(t => `reply-${t.id}` === id);
  if (found) s.openTrace(found.id); else ElMessage.info('未找到关联记录');
}
</script>
<template>
  <el-dialog v-model="open" title="回复路由详情" width="min(1180px, 96vw)" top="3vh"
    class="wb-dialog pv-reply-dialog" append-to-body destroy-on-close>
    <template v-if="snapshot && trace">
      <div class="pv-reply-toolbar"><button class="wb-text-button" @click="s.openRecord(trace.conversationId);s.traceId.value=null">查看完整会话 →</button></div>
      <TraceDetailView :key="`${trace.id}-${revision}`" :detail="snapshot.detail" embedded :load-payload="loadPayload"
        :token-usage="{input:trace.input,output:trace.output}" @refresh="revision++" @open="related"
        @error="ElMessage.error('读取回复路由失败，请重试')" />
    </template>
    <div v-else class="pv-empty"><strong>未找到对应回复路由</strong></div>
  </el-dialog>
</template>
