<script setup lang="ts">
import { ref, watch } from "vue";
import { api } from "../../api";
import type { AdminProps } from "../../domain/roles";
const props = defineProps<AdminProps>(),
  emit = defineEmits<{ error: [unknown]; navigate: [string] }>();
const docs = ref<{ id: number; current_version_id: number | null }[]>([]),
  drafts = ref(0),
  failed = ref(0);
const testQuestion = ref(''), testType = ref(''), testCategory = ref(''),
  testResults = ref<{ chunk_id: number; section: string; content: string; source: string;
    document_version_id: number; tags: Record<string, string> }[]>([]), testing = ref(false);
async function testSearch() {
  if (!props.accountId || !testQuestion.value.trim()) return;
  testing.value = true;
  try {
    const params = new URLSearchParams({ account_id: String(props.accountId), q: testQuestion.value.trim() });
    if (testType.value.trim()) params.set('type', testType.value.trim());
    if (testCategory.value.trim()) params.set('category', testCategory.value.trim());
    testResults.value = await api(`/api/admin/knowledge/test-search?${params}`, 'GET', undefined, props.token);
  } catch (e) { emit('error', e); }
  finally { testing.value = false; }
}
async function load() {
  try {
    docs.value = await api(
      `/api/admin/documents${props.accountId ? `?account_id=${props.accountId}` : ''}`,
      "GET",
      undefined,
      props.token,
    );
    const versions = await Promise.all(
      docs.value.map((doc) =>
        api<{ status: string }[]>(
          `/api/admin/documents/${doc.id}/versions`,
          "GET",
          undefined,
          props.token,
        ),
      ),
    );
    drafts.value = versions.flat().filter((v) => v.status === "DRAFT").length;
    failed.value = versions.flat().filter((v) => v.status === "FAILED").length;
  } catch (e) {
    emit("error", e);
  }
}
watch(() => props.accountId, () => { testResults.value = []; load(); }, { immediate: true });
</script>
<template>
  <el-card shadow="never"
    ><template #header>知识库概览</template>
    <div class="stats">
      <div>
        <b>{{ docs.length }}</b
        ><small>文档</small>
      </div>
      <div>
        <b>{{ docs.filter((d) => d.current_version_id).length }}</b
        ><small>已发布</small>
      </div>
      <div>
        <b>{{ drafts }}</b
        ><small>待发布版本</small>
      </div>
      <div>
        <b>{{ failed }}</b
        ><small>解析失败</small>
      </div>
    </div>
    <div class="page-links row">
      <el-button @click="emit('navigate', 'documents')">管理文档</el-button
      ><el-button @click="emit('navigate', 'documents')">文档与解析状态</el-button>
    </div></el-card
  >
  <el-card shadow="never" style="margin-top:16px">
    <template #header>知识检索测试</template>
    <p class="muted">先在顶部选择接入账号。测试只检索此时生效的已发布版本，可按切片类型和商品类目过滤。</p>
    <div class="row" style="flex-wrap:wrap">
      <el-input v-model="testQuestion" placeholder="输入问题，如：七天无理由退货" style="width:320px" @keyup.enter="testSearch" />
      <el-input v-model="testType" placeholder="类型标签（可选）" style="width:170px" />
      <el-input v-model="testCategory" placeholder="商品类目（可选）" style="width:170px" />
      <el-button type="primary" :disabled="!props.accountId || !testQuestion.trim()" :loading="testing" @click="testSearch">检索测试</el-button>
    </div>
    <el-empty v-if="!testResults.length" description="暂无结果" />
    <div v-for="row in testResults" :key="row.chunk_id" class="chunk" style="border-top:1px solid #e4e7ed;margin-top:12px;padding-top:12px">
      <strong>{{ row.section || `切片 #${row.chunk_id}` }}</strong>
      <small> · 版本 #{{ row.document_version_id }} · {{ row.source }} · {{ row.tags }}</small>
      <p>{{ row.content }}</p>
    </div>
  </el-card>
</template>
