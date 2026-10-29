<script setup lang="ts">
import { ref, watch } from "vue";
import { api } from "../../api";
import type { AdminProps } from "../../domain/roles";
const props = defineProps<AdminProps>(),
  emit = defineEmits<{ error: [unknown] }>();
const metrics = ref<Record<string, number | null>>({}),
  loading = ref(false);
const labels: Record<string, string> = {
  conversations: "会话数",
  handoffs: "转人工数",
  handoff_rate: "转人工率",
  engaged_conversations: "有提问会话数",
  first_question_resolution_rate: "首问解决率（代理）",
  negative_feedback_rate: "用户差评率",
  average_customer_turns: "平均会话轮次",
  closed_conversations_with_questions: "已结束且有提问会话",
  rated_answers: "已评价回答数",
  negative_feedback: "点踩数",
  ai_failures: "智能客服失败数",
  knowledge_misses: "知识未命中",
  tool_success_rate: "工具成功率",
};
async function load() {
  loading.value = true;
  try {
    metrics.value = await api(
      `/api/admin/dashboard${props.accountId ? `?account_id=${props.accountId}` : ''}`,
      "GET",
      undefined,
      props.token,
    );
  } catch (e) {
    emit("error", e);
  } finally {
    loading.value = false;
  }
}
watch(() => props.accountId, load, { immediate: true });
</script>
<template>
  <el-card shadow="never" v-loading="loading"
    ><template #header>运营概览</template>
    <div class="stats">
      <div v-for="(value, key) in metrics" :key="key">
        <b>{{
          value === null
            ? "—"
              : key.endsWith("_rate")
              ? `${(value * 100).toFixed(1)}%`
              : value
        }}</b
        ><small>{{ labels[key] || key }}</small>
      </div>
    </div><p class="metric-note">首问解决率：已结束且有提问的会话中，仅一轮客户提问、智能客服已答复且未转人工的比例。转人工率和平均轮次以有提问的会话为分母；差评率以已评价回答为分母。</p></el-card
  >
</template>
<style scoped>
.metric-note { color: #68798d; font-size: 12px; line-height: 1.6; margin: 14px 0 0; }
</style>
