<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import { ElMessageBox } from "element-plus/es/components/message-box/index.mjs";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";
import { api } from "../../api";
import ListPage from "../../components/admin/ListPage.vue";
import { useLocalList } from "../../composables/useLocalList";
import type { AdminProps } from "../../domain/roles";
const props = defineProps<AdminProps>(),
  emit = defineEmits<{ error: [unknown] }>();
type Row = {
  id: number;
  kind: string;
  value: Record<string, unknown>;
  version?: number;
  status?: string;
  key?: string;
  updated_at?: string;
};
const rows = ref<Row[]>([]),
  loading = ref(false),
  saving = ref(false),
  visible = ref(false),
  value = ref(""),
  promptKey = ref(""),
  promptValue = ref(""),
  editingPrompt = ref(false),
  llmModel = ref(""),
  ragDraft = ref({final_top_k:5});
const kind = computed(() => props.page.slice(7)),
  editable = computed(() => ["SUPER_ADMIN", "ADMIN"].includes(props.role));
const configTitle = computed(() => ({model:"LLM 配置",prompt:"Prompt 模板",rag:"检索参数"}[kind.value] || "配置版本"));
const configDescription = computed(() => kind.value === "model"
  ? "只在此处配置 LLM 模型名；服务地址和 API 凭据由服务端环境变量管理。"
  : kind.value === "rag"
    ? "设置检索返回的知识片段数；切片长度和重叠长度在“模型与向量”中管理。"
    : kind.value === "prompt" ? "每个 Key 单独保存，保存后立即用于后续会话。"
      : "配置保存为草稿，发布后生效。");
const { keyword, page, pageSize, data, total, query, reset } =
  useLocalList(rows);
async function load() {
  loading.value = true;
  try {
    if (kind.value === "prompt") {
      const prompts = await api<{ id: number; key: string; value: string; updated_at: string | null }[]>(
        "/api/admin/prompts", "GET", undefined, props.token);
      rows.value = prompts.map((row) => ({ id: row.id, kind: "prompt", key: row.key,
        value: { prompt_text: row.value }, status: "ACTIVE", updated_at: row.updated_at || undefined }));
    } else {
      rows.value = (await api<Row[]>("/api/admin/configs", "GET", undefined, props.token))
        .filter((row) => row.kind === kind.value);
    }
  } catch (e) {
    emit("error", e);
  } finally {
    loading.value = false;
  }
}
function open(row?: Row) {
  if (kind.value === "prompt") {
    editingPrompt.value = !!row;
    promptKey.value = row?.key || "";
    promptValue.value = String(row?.value.prompt_text || "");
    visible.value = true;
    return;
  }
  const currentValue = rows.value.find((row) => row.status === "PUBLISHED")?.value ||
      (kind.value === "model"
        ? { llm_model: "" }
        : kind.value === "rag"
          ? { final_top_k: 5, target_chars:800, overlap_chars:100 }
          : {});
  value.value = JSON.stringify(currentValue, null, 2);
  if (kind.value === "model") llmModel.value = String(currentValue.llm_model || "");
  if (kind.value === "rag") ragDraft.value = {
    final_top_k: Number(currentValue.final_top_k || 5),
  };
  visible.value = true;
}
async function save() {
  if (saving.value) return;
  saving.value = true;
  try {
    if (kind.value === "prompt") {
      const key = promptKey.value.trim();
      if (!/^[a-z][a-z0-9_]{1,63}$/.test(key) || !promptValue.value.trim()) {
        ElMessage.warning("请填写合法的 Prompt Key 和内容");
        return;
      }
      await api(`/api/admin/prompts/${encodeURIComponent(key)}`, "PUT", { value: promptValue.value }, props.token);
    } else await api(
      "/api/admin/configs",
      "POST",
      { kind: kind.value, value: kind.value === "rag"
        ? { final_top_k: ragDraft.value.final_top_k }
        : kind.value === "model" ? { llm_model: llmModel.value.trim() }
          : JSON.parse(value.value) },
      props.token,
    );
    ElMessage.success(kind.value === "prompt" ? "Prompt 已保存并生效" : "配置草稿已保存");
    visible.value = false;
    await load();
  } catch (e) {
    emit("error", e);
  } finally {
    saving.value = false;
  }
}
async function deletePrompt(row: Row) {
  try {
    await ElMessageBox.confirm(`删除 Prompt「${row.key}」？后续会话将不再读取此 Key。`, "删除 Prompt", {
      confirmButtonText: "删除", cancelButtonText: "取消", type: "warning",
    });
    await api(`/api/admin/prompts/${encodeURIComponent(row.key || "")}`, "DELETE", undefined, props.token);
    ElMessage.success("Prompt 已删除");
    await load();
  } catch (e) {
    if (e !== "cancel" && e !== "close") emit("error", e);
  }
}
async function publish(id: number) {
  try {
    await ElMessageBox.confirm(
      "发布后将影响后续会话。确认发布此版本？",
      "发布配置",
      { confirmButtonText: "发布", cancelButtonText: "取消" },
    );
    await api(`/api/admin/configs/${id}/publish`, "POST", {}, props.token);
    ElMessage.success("发布成功");
    await load();
  } catch (e) {
    if (e !== "cancel" && e !== "close") emit("error", e);
  }
}
onMounted(load);
</script>
<template>
  <ListPage
    :title="configTitle"
    :description="configDescription"
    :loading="loading"
    :total="total"
    v-model:page="page"
    v-model:page-size="pageSize"
    ><template #actions
      ><el-button v-if="editable" type="primary" @click="open()"
        >{{ kind === 'prompt' ? '新增 Prompt' : '新增版本' }}</el-button
      ></template
    ><template #filters
      ><el-input
        v-model="keyword"
        clearable
        placeholder="版本 / 状态 / 配置内容"
        @keyup.enter="query"
      /><el-button type="primary" @click="query">查询</el-button
      ><el-button @click="reset">重置</el-button></template
    ><el-table :data="data" border stripe
      ><el-table-column v-if="kind === 'prompt'" prop="key" label="Key" width="220" />
      <el-table-column v-else
        prop="version"
        label="版本"
        width="90"
      /><el-table-column
        v-if="kind !== 'prompt'"
        prop="status"
        label="状态"
        width="140"
      /><el-table-column v-if="kind === 'prompt'" label="Prompt 内容" min-width="300"
        ><template #default="{ row }"><pre class="config-preview">{{ row.value.prompt_text }}</pre></template>
      </el-table-column><el-table-column v-if="kind === 'prompt'" prop="updated_at" label="更新时间" width="190" />
      <el-table-column v-else label="配置内容" min-width="300"
        ><template #default="{ row }">
          <pre class="config-preview">{{
            JSON.stringify(kind === 'model' ? { llm_model: row.value.llm_model }
              : kind === 'rag' ? { final_top_k: row.value.final_top_k } : row.value, null, 2)
          }}</pre>
        </template></el-table-column
      ><el-table-column v-if="editable" label="操作" :width="kind === 'prompt' ? 150 : 100" fixed="right"
        ><template #default="{ row }"
          ><template v-if="kind === 'prompt'"><el-button link type="primary" @click="open(row)">编辑</el-button>
            <el-button v-if="!['routing_instruction', 'knowledge_instruction'].includes(row.key || '')" link type="danger" @click="deletePrompt(row)">删除</el-button></template>
          <template v-else><el-button
            v-if="row.status === 'DRAFT'"
            link
            type="primary"
            @click="publish(row.id)"
            >发布</el-button
          ><span v-else class="muted">已发布</span></template></template
        ></el-table-column
      ></el-table
    ></ListPage
  ><el-dialog
    v-model="visible"
    :title="kind === 'prompt' ? (editingPrompt ? '编辑 Prompt' : '新增 Prompt') : '新增配置版本'"
    width="650px"
    :close-on-click-modal="false"
    ><el-form label-position="top"
      ><el-form-item v-if="kind === 'model'" label="LLM 模型">
        <el-input v-model="llmModel" placeholder="如 deepseek-flash" />
      </el-form-item>
      <el-form-item v-if="kind === 'rag'" label="检索参数">
        <div class="rag-config-form">
          <label>最终知识片段数 <el-input-number v-model="ragDraft.final_top_k" :min="1" :max="10" /></label>
        </div>
      </el-form-item>
      <template v-if="kind === 'prompt'"><el-form-item label="Key">
        <el-input v-model="promptKey" :disabled="editingPrompt" placeholder="例如 routing_instruction" />
      </el-form-item><el-form-item label="Prompt 内容">
        <el-input v-model="promptValue" type="textarea" :rows="12" placeholder="请输入 Prompt 内容" />
      </el-form-item></template>
    </el-form
    ><template #footer
      ><el-button @click="visible = false">取消</el-button
      ><el-button type="primary" :loading="saving" @click="save"
        >{{ kind === 'prompt' ? '保存并立即生效' : '保存草稿' }}</el-button
      ></template
    ></el-dialog
  >
</template>

<style scoped>
.rag-config-form{display:flex;flex-direction:column;gap:16px;width:100%}.rag-config-form label{display:flex;align-items:center;justify-content:space-between;gap:16px}
</style>
