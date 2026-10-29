<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import "element-plus/es/components/message/style/css";
import type { FormInstance } from "element-plus/es/components/form/index.mjs";
import { api } from "../../api";
import type { AdminProps } from "../../domain/roles";
const props = defineProps<AdminProps>(),
  emit = defineEmits<{ error: [unknown]; navigate: [string] }>();
const form = reactive({ title: "", question: "", answer: "" }),
  formRef = ref<FormInstance>(),
  saving = ref(false);
const scope = ref(props.accountId ? 'ACCOUNT' : 'GLOBAL');
const targetAccountId = ref<number | null>(props.accountId || null);
const targetPlatform = ref<string | null>(null);
const accounts = ref<{ id: number; name: string; platform_name: string }[]>([]);
const platforms = ref<{ code: string; name: string }[]>([]);
onMounted(async () => {
  try {
    [accounts.value, platforms.value] = await Promise.all([
      api<typeof accounts.value>('/api/admin/accounts', 'GET', undefined, props.token),
      api<typeof platforms.value>('/api/admin/platforms', 'GET', undefined, props.token),
    ]);
  } catch (error) { emit('error', error); }
});
const editable = computed(() =>
  ["SUPER_ADMIN", "ADMIN", "KNOWLEDGE_MANAGER"].includes(props.role),
);
async function save() {
  if (saving.value || !(await formRef.value?.validate().catch(() => false)))
    return;
  saving.value = true;
  try {
    if (scope.value === 'ACCOUNT' && !targetAccountId.value) { saving.value = false; ElMessage.warning('请选择账号'); return; }
    if (scope.value === 'PLATFORM' && !targetPlatform.value) { saving.value = false; ElMessage.warning('请选择平台'); return; }
    await api("/api/admin/faq", "POST", { ...form,
      account_id: scope.value === 'ACCOUNT' ? targetAccountId.value : null,
      platform_code: scope.value === 'PLATFORM' ? targetPlatform.value : null }, props.token);
    ElMessage.success("FAQ 草稿已保存");
    emit("navigate", "documents");
  } catch (e) {
    emit("error", e);
  } finally {
    saving.value = false;
  }
}
</script>
<template>
  <el-card shadow="never"
    ><template #header>新增 FAQ</template
    ><el-form
      ref="formRef"
      :model="form"
      label-width="90px"
      class="editor-form"
      :disabled="!editable"
      @submit.prevent="save"
      ><el-form-item label="适用范围">
        <el-select v-model="scope" style="width:180px"><el-option label="全局通用" value="GLOBAL" />
          <el-option label="指定平台" value="PLATFORM" /><el-option label="指定账号" value="ACCOUNT" /></el-select>
        <el-select v-if="scope === 'ACCOUNT'" v-model="targetAccountId" placeholder="选择账号" style="width:230px;margin-left:8px">
          <el-option v-for="account in accounts" :key="account.id" :value="account.id" :label="`${account.platform_name} · ${account.name}`" /></el-select>
        <el-select v-if="scope === 'PLATFORM'" v-model="targetPlatform" placeholder="选择平台" style="width:230px;margin-left:8px">
          <el-option v-for="platform in platforms" :key="platform.code" :value="platform.code" :label="platform.name" /></el-select>
      </el-form-item><el-form-item
        v-for="field in ['title', 'question', 'answer'] as const"
        :key="field"
        :label="{ title: '标题', question: '问题', answer: '答案' }[field]"
        :prop="field"
        :rules="[{ required: true, message: '请填写此项', trigger: 'blur' }]"
        ><el-input
          v-model="form[field]"
          :type="field === 'answer' ? 'textarea' : 'text'"
          :rows="6"
          :maxlength="
            field === 'answer' ? 10000 : field === 'question' ? 1000 : 255
          " /></el-form-item
      ><el-form-item
        ><el-button type="primary" :loading="saving" @click="save"
          >保存草稿</el-button
        ></el-form-item
      ></el-form
    ></el-card
  >
</template>
