<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import { ElMessageBox } from "element-plus/es/components/message-box/index.mjs";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";
import { api } from "../../api";
import ListPage from "../../components/admin/ListPage.vue";
import { useLocalList } from "../../composables/useLocalList";
import type { AdminProps } from "../../domain/roles";
import { formatLocalDateTime } from "../../domain/datetime";
const props = defineProps<AdminProps>(),
  emit = defineEmits<{ error: [unknown] }>();
type Row = {
  id: number;
  title: string;
  account_id: number | null;
  platform_code: string | null;
  current_version_id: number | null;
  is_active: boolean;
  versions: { id: number; version: number; status: string; error?: string | null;
    chunk_count: number; vectorized_chunks: number; activation_state: string;
    effective_from?: string | null; effective_until?: string | null;
    auto_revert_on_expiry?: boolean }[];
};
type ChunkRow = { ordinal: number; section: string; content: string;
  tags: Record<string, string>; has_embedding?: boolean };
const rows = ref<Row[]>([]),
  loading = ref(false),
  busy = ref(false),
  reindexing = ref(false),
  uploadVisible = ref(false),
  upgradingDocumentId = ref<number | null>(null),
  upgradingDocument = ref<Row | null>(null),
  versionMode = ref<'DOCUMENT' | 'FAQ'>('DOCUMENT'),
  uploadPrepareOnly = ref(true),
  chunksVisible = ref(false),
  publishVisible = ref(false),
  selectedVersionId = ref<number | null>(null),
  selectedDraft = ref(false),
  publication = ref({ from: '', until: '', lexicalOnly: false, autoRevert: false }),
  hasPreviousPublishedVersion = ref(false),
  strategy = ref('semantic'),
  targetChars = ref(800),
  overlapChars = ref(100),
  file = ref<File | null>(null),
  chunks = ref<ChunkRow[]>([]),
  faq = ref({ title: '', question: '', answer: '' }),
  faqScope = ref<'GLOBAL' | 'PLATFORM' | 'ACCOUNT'>(props.accountId ? 'ACCOUNT' : 'GLOBAL'),
  faqPlatform = ref(''),
  platforms = ref<{ code: string; name: string }[]>([]);
const { keyword, page, pageSize, data, total, query, reset } =
  useLocalList(rows);
const editable = computed(() =>
  ["SUPER_ADMIN", "ADMIN", "KNOWLEDGE_MANAGER"].includes(props.role),
);
async function load() {
  loading.value = true;
  try {
    const configs = await api<{kind:string;status:string;value:Record<string, number>}[]>("/api/admin/configs", "GET", undefined, props.token);
    const activeRag = configs.find(row => row.kind === 'rag' && row.status === 'PUBLISHED')?.value;
    if (activeRag) {
      targetChars.value = activeRag.target_chars || 800;
      overlapChars.value = activeRag.overlap_chars ?? 100;
    }
    const docs = await api<Omit<Row, "versions">[]>(
      `/api/admin/documents${props.accountId ? `?account_id=${props.accountId}` : ''}`,
      "GET",
      undefined,
      props.token,
    );
    rows.value = await Promise.all(
      docs.map(async (doc) => ({
        ...doc,
        versions: await api<Row["versions"]>(
          `/api/admin/documents/${doc.id}/versions`,
          "GET",
          undefined,
          props.token,
        ),
      })),
    );
  } catch (e) {
    emit("error", e);
  } finally {
    loading.value = false;
  }
}
async function syncPublishedKnowledge() {
  if (reindexing.value || busy.value) return;
  try {
    await ElMessageBox.confirm(
      "系统将从 MySQL 读取当前商户全部已发布知识版本，并写入或更新 OpenSearch。此操作不会重新生成向量，也不会修改版本状态。",
      "同步已发布知识",
      { type: "warning", confirmButtonText: "开始同步", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }

  reindexing.value = true;
  try {
    const result = await api<{ published_versions: number; indexed_chunks: number; missing_embeddings: number }>(
      "/api/admin/knowledge/reindex", "POST", {}, props.token,
    );
    if (result.missing_embeddings > 0) {
      ElMessage.warning(
        `已同步 ${result.published_versions} 个版本、${result.indexed_chunks} 个切片；其中 ${result.missing_embeddings} 个切片没有向量，语义检索可能不完整。`,
      );
    } else {
      ElMessage.success(
        `同步完成：${result.published_versions} 个已发布版本、${result.indexed_chunks} 个切片。`,
      );
    }
  } catch (e) {
    emit("error", e);
  } finally {
    reindexing.value = false;
  }
}
async function preview(id: number, status: string) {
  try {
    selectedVersionId.value = id;
    selectedDraft.value = status === 'DRAFT';
    chunks.value = await api<ChunkRow[]>(
      `/api/admin/versions/${id}/chunks`,
      "GET",
      undefined,
      props.token,
    );
    chunksVisible.value = true;
  } catch (e) {
    emit("error", e);
  }
}
async function suggest() {
  if (!selectedVersionId.value) return;
  busy.value = true;
  try {
    chunks.value = await api<ChunkRow[]>(`/api/admin/versions/${selectedVersionId.value}/chunks/suggest`,
      'POST', { strategy: strategy.value, target_chars: targetChars.value,
        overlap_chars: overlapChars.value }, props.token);
    ElMessage.success('已生成候选切片；请检查后保存');
  } catch (e) { emit('error', e); }
  finally { busy.value = false; }
}
async function saveChunks() {
  if (!selectedVersionId.value) return;
  busy.value = true;
  try {
    await api(`/api/admin/versions/${selectedVersionId.value}/chunks`, 'PUT',
      { chunks: chunks.value.map(c => ({ section: c.section, content: c.content, tags: c.tags || {} })) }, props.token);
    ElMessage.success('切片已保存，请单独执行向量化');
    await preview(selectedVersionId.value, 'DRAFT');
    await load();
  } catch (e) { emit('error', e); }
  finally { busy.value = false; }
}
async function vectorize() {
  if (!selectedVersionId.value) return;
  busy.value = true;
  try {
    await api(`/api/admin/versions/${selectedVersionId.value}/embed`, 'POST', {}, props.token);
    ElMessage.success('向量化完成');
    await preview(selectedVersionId.value, 'DRAFT');
    await load();
  } catch (e) { emit('error', e); }
  finally { busy.value = false; }
}
function openPublish(id: number, currentVersion: number, versions: Row['versions']) {
  selectedVersionId.value = id;
  hasPreviousPublishedVersion.value = versions.some(v => v.version < currentVersion && ['PUBLISHED', 'ARCHIVED'].includes(v.status));
  publication.value = { from: '', until: '', lexicalOnly: false, autoRevert: false };
  publishVisible.value = true;
}
async function publishVersion() {
  if (!selectedVersionId.value) return;
  busy.value = true;
  try {
    const body = { effective_from: publication.value.from ? new Date(publication.value.from).toISOString() : null,
      effective_until: publication.value.until ? new Date(publication.value.until).toISOString() : null,
      auto_revert_on_expiry: !!publication.value.until && hasPreviousPublishedVersion.value && publication.value.autoRevert,
      allow_lexical_only: publication.value.lexicalOnly };
    const result = await api<{ status: string }>(`/api/admin/versions/${selectedVersionId.value}/publish`, 'POST', body, props.token);
    publishVisible.value = false;
    ElMessage.success(result.status === 'SCHEDULED' ? '已安排定时生效' : '发布成功');
    await load();
  } catch (e) { emit('error', e); }
  finally { busy.value = false; }
}
async function action(id: number, name: string) {
  if (busy.value) return;
  busy.value = true;
  try {
    await api(`/api/admin/versions/${id}/${name}`, "POST", {}, props.token);
    ElMessage.success(name === 'rollback' ? '已回滚到该版本' : '已重试');
    await load();
  } catch (e) {
    emit("error", e);
  } finally {
    busy.value = false;
  }
}
async function upload() {
  if (!file.value || busy.value) return;
  busy.value = true;
  try {
    const body = new FormData();
    body.append("file", file.value);
    body.append('prepare_only', uploadPrepareOnly.value ? 'true' : 'false');
    if (upgradingDocumentId.value) body.append('document_id', String(upgradingDocumentId.value));
    else if (props.accountId) body.append('account_id', String(props.accountId));
    await api("/api/admin/documents/upload", "POST", body, props.token);
    uploadVisible.value = false;
    upgradingDocumentId.value = null;
    file.value = null;
    ElMessage.success("草稿已创建");
    await load();
  } catch (e) {
    emit("error", e);
  } finally {
    busy.value = false;
  }
}
function openUpgrade(row: Row) {
  upgradingDocumentId.value = row.id;
  upgradingDocument.value = row;
  versionMode.value = 'DOCUMENT';
  uploadPrepareOnly.value = true;
  file.value = null;
  faq.value = { title: row.title, question: '', answer: '' };
  uploadVisible.value = true;
}
async function saveFaq() {
  if (busy.value) return;
  if (!faq.value.title.trim() || !faq.value.question.trim() || !faq.value.answer.trim()) {
    ElMessage.warning('请填写 FAQ 标题、问题和答案');
    return;
  }
  busy.value = true;
  try {
    const isUpgradeFaq = !!upgradingDocument.value;
    if (!upgradingDocument.value && faqScope.value === 'ACCOUNT' && !props.accountId) {
      ElMessage.warning('请先在顶部选择接入账号');
      return;
    }
    if (!upgradingDocument.value && faqScope.value === 'PLATFORM' && !faqPlatform.value) {
      ElMessage.warning('请选择适用平台');
      return;
    }
    await api('/api/admin/faq', 'POST', { ...faq.value,
      document_id: upgradingDocumentId.value,
      account_id: upgradingDocument.value?.account_id ?? (faqScope.value === 'ACCOUNT' ? props.accountId : null),
      platform_code: upgradingDocument.value?.platform_code ?? (faqScope.value === 'PLATFORM' ? faqPlatform.value : null) }, props.token);
    uploadVisible.value = false;
    upgradingDocumentId.value = null;
    upgradingDocument.value = null;
    faq.value = { title: '', question: '', answer: '' };
    ElMessage.success(isUpgradeFaq ? 'FAQ 新版本草稿已创建' : 'FAQ 草稿已创建，可在文档版本中继续切片和发布');
    await load();
  } catch (e) { emit('error', e); }
  finally { busy.value = false; }
}
async function openFaq() {
  upgradingDocumentId.value = null;
  upgradingDocument.value = null;
  versionMode.value = 'FAQ';
  faq.value = { title: '', question: '', answer: '' };
  faqScope.value = props.accountId ? 'ACCOUNT' : 'GLOBAL';
  faqPlatform.value = '';
  uploadVisible.value = true;
  try { platforms.value = await api('/api/admin/platforms', 'GET', undefined, props.token); }
  catch (e) { emit('error', e); }
}
async function setActive(row: Row, active: boolean) {
  try {
    await api(`/api/admin/documents/${row.id}/active`, 'PUT', { active }, props.token);
    ElMessage.success(active ? '文档已启用' : '文档已停用，检索将立即忽略它');
    await load();
  } catch (e) { emit('error', e); }
}
async function removeDocument(row: Row) {
  try {
    await ElMessageBox.confirm(`确定永久删除“${row.title}”及其全部历史版本、切片和原始文件吗？此操作不可恢复。`, '删除知识文档', { type: 'warning', confirmButtonText: '永久删除' });
    await api(`/api/admin/documents/${row.id}`, 'DELETE', undefined, props.token);
    ElMessage.success('文档及其版本已删除');
    await load();
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') emit('error', e);
  }
}
onMounted(load);
watch(() => props.accountId, load);
</script>
<template>
  <ListPage
    title="知识文档与版本"
    description="FAQ 与上传文档统一管理。已发布内容通过新建版本修改：上传新版本、检查切片并向量化，确认后发布；旧版本保留，可随时回滚。停用会立即停止检索，删除会永久清除文档及全部版本。"
    :loading="loading"
    :total="total"
    v-model:page="page"
    v-model:page-size="pageSize"
  >
    <template #actions
      ><el-button v-if="editable && props.page === 'documents'" :loading="reindexing" :disabled="busy" @click="syncPublishedKnowledge">同步已发布知识</el-button><el-button v-if="editable && props.page === 'documents'" @click="openFaq">新增 FAQ</el-button><el-button
        v-if="editable && props.page === 'documents'"
        type="primary"
        @click="uploadVisible = true"
        >上传文档</el-button
      ></template
    >
    <template #filters
      ><el-input
        v-model="keyword"
        clearable
        placeholder="文档标题 / 解析状态"
        @keyup.enter="query"
      /><el-button type="primary" @click="query">查询</el-button
      ><el-button @click="reset">重置</el-button></template
    >
    <el-table :data="data" border stripe row-key="id">
      <el-table-column type="expand"
        ><template #default="{ row }"
          ><div class="expanded-table">
            <el-table :data="row.versions" border
              ><el-table-column
                prop="version"
                label="版本"
                width="90"
              /><el-table-column
                prop="status"
                label="解析 / 发布状态"
                min-width="140"
              /><el-table-column label="向量" width="110"
                ><template #default="{ row: version }">{{ version.vectorized_chunks }}/{{ version.chunk_count }}</template>
              </el-table-column><el-table-column label="生效状态" width="120"
                ><template #default="{ row: version }">{{ { ACTIVE: '当前生效', SCHEDULED: '等待生效', INACTIVE: '未生效' }[version.activation_state as 'ACTIVE' | 'SCHEDULED' | 'INACTIVE'] }}</template>
              </el-table-column><el-table-column label="生效 / 失效" min-width="250"
                ><template #default="{ row: version }">{{ formatLocalDateTime(version.effective_from) }} / {{ version.effective_until ? formatLocalDateTime(version.effective_until) : '长期' }}{{ version.auto_revert_on_expiry ? ' · 到期恢复上版' : '' }}</template>
              </el-table-column><el-table-column label="提示" min-width="230" show-overflow-tooltip
                ><template #default="{ row: version }">{{ version.error || '—' }}</template>
              </el-table-column><el-table-column label="操作" min-width="240"
                ><template #default="{ row: version }"
                  ><el-button link type="primary" @click="preview(version.id, version.status)"
                    >{{ version.status === 'DRAFT' ? '编辑切片' : '查看切片' }}</el-button
                  ><el-button
                    v-if="editable && version.status === 'DRAFT'"
                    link
                    type="primary"
                    :disabled="busy"
                    @click="openPublish(version.id, version.version, row.versions)"
                    >发布</el-button
                  ><el-button v-if="editable && (version.status === 'PUBLISHED' || version.status === 'ARCHIVED') && version.activation_state !== 'ACTIVE'"
                    link type="primary" :disabled="busy" @click="action(version.id, 'rollback')">回滚至此</el-button
                  ><el-button
                    v-if="editable && version.status === 'FAILED'"
                    link
                    type="primary"
                    :disabled="busy"
                    @click="action(version.id, 'retry')"
                    >重试</el-button
                  ></template
                ></el-table-column
              ></el-table
            >
          </div></template
        ></el-table-column
      >
      <el-table-column prop="id" label="ID" width="85" /><el-table-column
        prop="title"
        label="文档标题"
        min-width="240"
        show-overflow-tooltip
      /><el-table-column label="适用范围" width="140"><template #default="{row}">
        {{ row.account_id ? `账号 #${row.account_id}` : row.platform_code ? `平台 ${row.platform_code}` : '全局通用' }}
      </template></el-table-column><el-table-column label="当前发布版本" width="150"
        ><template #default="{ row }">{{
          row.current_version_id
            ? `V${row.versions.find((v: any) => v.id === row.current_version_id)?.version || "—"}`
            : "未发布"
        }}</template></el-table-column
      ><el-table-column label="最新状态" width="150"
        ><template #default="{ row }"
          ><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? (row.versions[0]?.status || '无版本') : '已停用' }}</el-tag></template
        ></el-table-column
      >
      <el-table-column v-if="editable" label="操作" width="230" fixed="right"><template #default="{ row }">
        <el-button link type="primary" @click="openUpgrade(row)">新建版本</el-button>
        <el-button link :type="row.is_active ? 'warning' : 'success'" @click="setActive(row, !row.is_active)">{{ row.is_active ? '停用' : '启用' }}</el-button>
        <el-button link type="danger" @click="removeDocument(row)">删除</el-button>
      </template></el-table-column>
    </el-table>
  </ListPage>
  <el-dialog
    v-model="uploadVisible"
    :title="upgradingDocument ? `新建版本 · ${upgradingDocument.title}` : '新增知识内容'"
    width="540px"
    destroy-on-close
    :close-on-click-modal="false"
    ><el-radio-group v-if="upgradingDocument" v-model="versionMode" style="margin-bottom:16px"><el-radio-button value="DOCUMENT">上传文档</el-radio-button><el-radio-button value="FAQ">FAQ</el-radio-button></el-radio-group>
    <p v-if="versionMode === 'DOCUMENT'" class="muted">支持 TXT、Markdown、CSV、HTML、DOCX、PDF、XLSX。{{ upgradingDocumentId ? '此操作将为原文档创建新版本，旧发布版本继续生效，直至新版本发布。' : '上传同名同范围文档会创建新版本。' }}</p>
    <input v-if="versionMode === 'DOCUMENT'"
      type="file"
      accept=".txt,.md,.csv,.html,.htm,.docx,.pdf,.xlsx"
      @change="file = ($event.target as HTMLInputElement).files?.[0] || null"
    /><div v-if="versionMode === 'DOCUMENT'" style="margin-top:14px"><el-checkbox v-model="uploadPrepareOnly">只解析原文，随后手动切片与向量化</el-checkbox></div>
    <el-form v-if="versionMode === 'FAQ'" label-width="90px" style="margin-top:16px">
      <el-form-item label="FAQ 标题"><el-input v-model="faq.title" :disabled="!!upgradingDocument" maxlength="255" placeholder="例如：拼多多退货政策" /></el-form-item>
      <el-form-item label="问题"><el-input v-model="faq.question" maxlength="1000" placeholder="客户可能会如何提问？" /></el-form-item>
      <el-form-item label="答案"><el-input v-model="faq.answer" type="textarea" :rows="5" maxlength="10000" placeholder="填写经审核的标准答案" /></el-form-item>
      <el-form-item label="适用范围"><span v-if="upgradingDocument">与原文档一致：{{ upgradingDocument.account_id ? `账号 #${upgradingDocument.account_id}` : upgradingDocument.platform_code || '全局通用' }}</span>
        <template v-else><el-select v-model="faqScope" style="width:190px"><el-option label="全局通用" value="GLOBAL" /><el-option label="指定平台" value="PLATFORM" /><el-option label="当前接入账号" value="ACCOUNT" /></el-select>
          <el-select v-if="faqScope === 'PLATFORM'" v-model="faqPlatform" placeholder="选择平台" style="width:190px;margin-left:8px"><el-option v-for="item in platforms" :key="item.code" :label="item.name" :value="item.code" /></el-select>
          <span v-if="faqScope === 'ACCOUNT'">{{ props.accountId ? `账号 #${props.accountId}` : '请先从顶部选择接入账号' }}</span></template>
      </el-form-item></el-form>
    <template #footer
      ><el-button @click="uploadVisible = false">取消</el-button
      ><el-button v-if="versionMode === 'DOCUMENT'"
        type="primary"
        :loading="busy"
        :disabled="!file"
        @click="upload"
        >上传草稿</el-button
      ><el-button v-else type="primary" :loading="busy" @click="saveFaq">{{ upgradingDocument ? '创建 FAQ 新版本' : '保存 FAQ 草稿' }}</el-button
      ></template
    ></el-dialog
  >
  <el-dialog v-model="chunksVisible" title="文档切片与向量化" width="900px" :close-on-click-modal="false"
    ><div v-if="selectedDraft && editable" class="row" style="margin-bottom:14px;flex-wrap:wrap">
      <el-select v-model="strategy" style="width:160px"><el-option label="业务段落" value="semantic" /><el-option label="指定长度" value="length" /><el-option label="AI 建议分组" value="ai" /></el-select>
      <label v-if="strategy === 'length'" style="display:flex;align-items:center;gap:8px;color:#606266;font-size:14px"><span>每片长度</span><el-input-number v-model="targetChars" :min="200" :max="4000" :step="100" /><small>字符</small></label>
      <label v-if="strategy === 'length'" style="display:flex;align-items:center;gap:8px;color:#606266;font-size:14px"><span>重叠长度</span><el-input-number v-model="overlapChars" :min="0" :max="1000" :step="20" /><small>字符</small></label>
      <el-button :loading="busy" @click="suggest">生成候选切片</el-button>
      <el-button @click="chunks.push({ ordinal: chunks.length, section: '', content: '', tags: {} })">添加切片</el-button>
    </div>
    <p v-if="selectedDraft && editable" class="muted">长度单位为字符；AI 仅建议原文段落分组，保存前请核对规则。标签日期使用 YYYY-MM-DD。</p>
    <el-empty v-if="!chunks.length" description="暂无切片；请选择切片方式生成候选" />
    <div v-for="(chunk, index) in chunks" :key="index" class="chunk" style="border:1px solid #e4e7ed;padding:12px;margin-bottom:12px">
      <div class="row" style="margin-bottom:8px"><strong>切片 {{ index + 1 }}</strong><el-tag>{{ chunk.has_embedding ? '已向量化' : '未向量化' }}</el-tag>
        <el-button v-if="selectedDraft && editable" link type="danger" @click="chunks.splice(index, 1)">删除</el-button></div>
      <template v-if="selectedDraft && editable">
        <el-input v-model="chunk.section" placeholder="业务段落标题" style="margin-bottom:8px" />
        <el-input v-model="chunk.content" type="textarea" :rows="5" placeholder="必须保留文档原文" style="margin-bottom:8px" />
        <div class="row" style="flex-wrap:wrap">
          <el-input v-model="chunk.tags.type" placeholder="类型：退换货" style="width:170px" />
          <el-input v-model="chunk.tags.category" placeholder="商品类目：手机" style="width:170px" />
          <el-input v-model="chunk.tags.valid_from" placeholder="标签生效：YYYY-MM-DD" style="width:190px" />
          <el-input v-model="chunk.tags.valid_until" placeholder="标签失效：YYYY-MM-DD" style="width:190px" />
        </div>
      </template><template v-else><small>{{ chunk.section }} · {{ chunk.tags }}</small><p>{{ chunk.content }}</p></template>
    </div>
    <template #footer><el-button @click="chunksVisible = false">关闭</el-button>
      <el-button v-if="selectedDraft && editable" :loading="busy" @click="saveChunks">保存切片</el-button>
      <el-button v-if="selectedDraft && editable" type="primary" :loading="busy" @click="vectorize">向量化已保存切片</el-button></template>
  </el-dialog>
  <el-dialog v-model="publishVisible" title="发布知识版本" width="520px" :close-on-click-modal="false">
    <p class="muted">留空生效时间表示立即生效；可指定失效时间。未来版本到时自动参与检索，无需覆盖旧索引。</p>
    <el-form label-width="90px"><el-form-item label="生效时间"><el-date-picker v-model="publication.from" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="立即生效" style="width:100%" /></el-form-item>
      <el-form-item label="失效时间"><el-date-picker v-model="publication.until" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="长期有效" style="width:100%" /></el-form-item>
      <el-form-item v-if="publication.until && hasPreviousPublishedVersion" label="到期处理"><el-checkbox v-model="publication.autoRevert">到期后自动恢复上一个已发布版本</el-checkbox></el-form-item>
      <el-form-item label="降级发布"><el-checkbox v-model="publication.lexicalOnly">明确允许无向量切片，仅做关键词检索</el-checkbox></el-form-item></el-form>
    <template #footer><el-button @click="publishVisible = false">取消</el-button><el-button type="primary" :loading="busy" @click="publishVersion">确认发布</el-button></template>
  </el-dialog
  >
</template>
