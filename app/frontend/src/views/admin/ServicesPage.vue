<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import { ElMessageBox } from "element-plus/es/components/message-box/index.mjs";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";
import { api } from "../../api";
import type { AdminProps } from "../../domain/roles";
const props = defineProps<AdminProps>(),
  emit = defineEmits<{ error: [unknown] }>();
type Services = {
  llm: { mode: string; model: string };
  embedding: { model: string; dimensions: number; configured: boolean };
  rerank: { model: string; configured: boolean };
  business: { mode: string };
  search: { configured: boolean };
  storage: string;
};
const info = ref<Services | null>(null),
  loading = ref(false),
  configs = ref<{id:number;kind:string;version:number;value:Record<string,any>;status:string}[]>([]),
  editorVisible = ref(false), saving = ref(false),
  draft = ref({embedding_model:'',embedding_dim:1024,rerank_model:'',target_chars:800,overlap_chars:100});
const publishedModel = computed(() => configs.value.find(row => row.kind === 'model' && row.status === 'PUBLISHED'));
const publishedRag = computed(() => configs.value.find(row => row.kind === 'rag' && row.status === 'PUBLISHED'));
const fields = computed(() =>
  !info.value
    ? []
    : props.page === "embedding"
      ? [
          ["向量模型", publishedModel.value?.value.embedding_model || info.value.embedding.model],
          ["向量维度", publishedModel.value?.value.embedding_dim || info.value.embedding.dimensions],
          [
            "Embedding 凭据",
            info.value.embedding.configured ? "已配置" : "未配置",
          ],
          ["Rerank 模型", publishedModel.value?.value.rerank_model || info.value.rerank.model],
          ["Rerank 凭据", info.value.rerank.configured ? "已配置" : "未配置"],
          ["切片长度", `${publishedRag.value?.value.target_chars ?? 800} 字符`],
          ["重叠长度", `${publishedRag.value?.value.overlap_chars ?? 100} 字符`],
        ]
      : [
          ["商户模式", "单商户"],
          [
            "电商模式",
            info.value.business.mode === "mock"
              ? "本地电商管理"
              : "HTTP 电商接口",
          ],
          ["LLM", `${info.value.llm.mode} / ${info.value.llm.model}`],
          [
            "搜索",
            info.value.search.configured ? "OpenSearch 已配置" : "MySQL 检索",
          ],
          ["文件存储", info.value.storage],
        ],
);
onMounted(async () => {
  loading.value = true;
  try {
    [info.value, configs.value] = await Promise.all([
      api<Services>("/api/admin/integrations", "GET", undefined, props.token),
      api<typeof configs.value>("/api/admin/configs", "GET", undefined, props.token),
    ]);
  } catch (e) {
    emit("error", e);
  } finally {
    loading.value = false;
  }
});
function openEditor() {
  const value = publishedModel.value?.value || {};
  draft.value = {
    embedding_model: value.embedding_model ?? info.value?.embedding.model ?? '',
    embedding_dim: value.embedding_dim ?? info.value?.embedding.dimensions ?? 1024,
    rerank_model: value.rerank_model ?? info.value?.rerank.model ?? '',
    target_chars: publishedRag.value?.value.target_chars ?? 800,
    overlap_chars: publishedRag.value?.value.overlap_chars ?? 100,
  };
  editorVisible.value = true;
}
async function saveModelConfig() {
  saving.value = true;
  try {
    const [modelDraft, ragDraft] = await Promise.all([
      api<{id:number}>("/api/admin/configs", "POST", {kind:"model", value:{
        embedding_model:draft.value.embedding_model,
        embedding_dim:draft.value.embedding_dim, rerank_model:draft.value.rerank_model,
      }}, props.token),
      api<{id:number}>("/api/admin/configs", "POST", {kind:"rag", value:{
        final_top_k:publishedRag.value?.value.final_top_k ?? 5,
        target_chars:draft.value.target_chars, overlap_chars:draft.value.overlap_chars,
      }}, props.token),
    ]);
    await Promise.all([
      api(`/api/admin/configs/${modelDraft.id}/publish`, "POST", {}, props.token),
      api(`/api/admin/configs/${ragDraft.id}/publish`, "POST", {}, props.token),
    ]);
    ElMessage.success("向量与切片参数已发布；更换向量模型或维度后，请重新向量化知识并重建索引");
    editorVisible.value = false;
    configs.value = await api<typeof configs.value>("/api/admin/configs", "GET", undefined, props.token);
  } catch (e) { emit("error", e); }
  finally { saving.value = false; }
}
</script>
<template>
  <el-card shadow="never" v-loading="loading"
    ><template #header>{{
      props.page === "embedding" ? "模型与向量" : "API 与服务"
    }}</template
    ><el-descriptions :column="1" border
      ><el-descriptions-item
        v-for="field in fields"
        :key="String(field[0])"
        :label="String(field[0])"
        >{{ field[1] || "未配置" }}</el-descriptions-item
      ></el-descriptions
    >
    <div v-if="props.page === 'embedding'" class="page-links row">
      <span class="list-note">LLM 模型请在“LLM”菜单配置。向量模型和维度覆盖服务端对应配置；切片参数用于后续文档处理。服务地址与 API 凭据由服务端环境变量管理。</span>
      <el-button v-if="['SUPER_ADMIN','ADMIN'].includes(props.role)" type="primary" @click="openEditor">编辑向量与切片参数</el-button>
    </div>
    <div v-else class="page-links row">
      <a
        href="http://127.0.0.1:8001/docs"
        target="_blank"
        rel="noopener noreferrer"
        >API 文档</a
      ><a
        href="http://127.0.0.1:5601/app/discover"
        target="_blank"
        rel="noopener noreferrer"
        >OpenSearch 可视化</a
      >
    </div></el-card>
  <el-dialog v-model="editorVisible" title="向量与切片参数" width="560px">
    <el-form label-width="130px">
      <el-form-item label="Embedding 模型"><el-input v-model="draft.embedding_model" placeholder="如 text-embedding-v4" /></el-form-item>
      <el-form-item label="向量维度"><el-input-number v-model="draft.embedding_dim" :min="1" :max="4096" /></el-form-item>
      <el-form-item label="Rerank 模型"><el-input v-model="draft.rerank_model" placeholder="如 qwen3.7-text-rerank" /></el-form-item>
      <el-form-item label="切片长度"><el-input-number v-model="draft.target_chars" :min="200" :max="4000" :step="100" /><span class="unit-label">字符</span></el-form-item>
      <el-form-item label="重叠长度"><el-input-number v-model="draft.overlap_chars" :min="0" :max="Math.min(1000, Math.ceil(draft.target_chars / 2) - 1)" :step="20" /><span style="margin-left:8px;color:#8492a5">字符</span></el-form-item>
    </el-form>
    <template #footer><el-button @click="editorVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveModelConfig">保存并发布</el-button></template>
  </el-dialog>
</template>
