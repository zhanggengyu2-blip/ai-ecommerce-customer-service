<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import 'element-plus/es/components/message/style/css';
import { api } from '../../api';
import type { AdminProps } from '../../domain/roles';
const props = defineProps<AdminProps>();
const emit = defineEmits<{ error: [unknown]; accountsChanged: [] }>();
type Account = { id: number; platform_code: string; platform_name: string; name: string; category: string; commerce_enabled: boolean; active: boolean };
type Platform = { code: string; name: string; category: string; commerce_enabled: boolean };
const rows = ref<Account[]>([]), platforms = ref<Platform[]>([]), loading = ref(false), saving = ref(false);
const staff = ref<{ id: number; display_name: string; username: string; role: string }[]>([]);
const selectedStaff = ref<number | null>(null), assigned = ref<number[]>([]);
const form = reactive({ platform_code: 'PINDUODUO', name: '', external_account_id: '' });
async function load() {
  loading.value = true;
  try {
    [rows.value, platforms.value, staff.value] = await Promise.all([
      api<Account[]>('/api/admin/accounts', 'GET', undefined, props.token),
      api<Platform[]>('/api/admin/platforms', 'GET', undefined, props.token),
      api<typeof staff.value>('/api/admin/users', 'GET', undefined, props.token).then(rows => rows.filter(row => row.role === 'CUSTOMER_SERVICE')),
    ]);
  } catch (error) { emit('error', error); }
  finally { loading.value = false; }
}
async function loadAccess() {
  if (!selectedStaff.value) return;
  try { assigned.value = await api<number[]>(`/api/admin/users/${selectedStaff.value}/accounts`, 'GET', undefined, props.token); }
  catch (error) { emit('error', error); }
}
async function saveAccess() {
  if (!selectedStaff.value) return;
  try {
    await api(`/api/admin/users/${selectedStaff.value}/accounts`, 'PUT', assigned.value, props.token);
    ElMessage.success('员工可接待账号已更新');
  } catch (error) { emit('error', error); }
}
async function save() {
  if (!form.name.trim() || saving.value) return;
  saving.value = true;
  try {
    await api('/api/admin/accounts', 'POST', { ...form, name: form.name.trim() }, props.token);
    form.name = ''; form.external_account_id = '';
    ElMessage.success('接入账号已创建');
    await load();
    emit('accountsChanged');
  } catch (error) { emit('error', error); }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<template>
  <el-card shadow="never" v-loading="loading">
    <template #header>接入账号</template>
    <p class="muted">平台下可有多个账号。自媒体账号默认只有会话与知识能力；真实平台授权和消息接口将在后续接入。</p>
    <div class="row" style="margin-bottom:16px">
      <el-select v-model="form.platform_code" style="width:180px">
        <el-option v-for="platform in platforms" :key="platform.code" :label="platform.name" :value="platform.code" />
      </el-select>
      <el-input v-model="form.name" placeholder="账号名称，例如拼多多主店" style="width:230px" />
      <el-input v-model="form.external_account_id" placeholder="平台账号 ID（可选）" style="width:220px" />
      <el-button type="primary" :loading="saving" @click="save">新增账号</el-button>
    </div>
    <el-table :data="rows" border stripe>
      <el-table-column prop="id" label="ID" width="75" />
      <el-table-column prop="platform_name" label="平台" width="150" />
      <el-table-column prop="name" label="账号名称" min-width="220" />
      <el-table-column label="类别" width="120"><template #default="{ row }">{{ row.category }}</template></el-table-column>
      <el-table-column label="电商数据" width="120"><template #default="{ row }">{{ row.commerce_enabled ? '可用' : '不适用' }}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }">{{ row.active ? '启用' : '停用' }}</template></el-table-column>
    </el-table>
  </el-card>
  <el-card shadow="never" style="margin-top:16px">
    <template #header>人工客服接待范围</template>
    <p class="muted">一个客服可勾选多个账号。未勾选的账号不会出现在该客服的队列中。</p>
    <div class="row">
      <el-select v-model="selectedStaff" placeholder="选择客服员工" style="width:220px" @change="loadAccess">
        <el-option v-for="person in staff" :key="person.id" :label="person.display_name || person.username" :value="person.id" />
      </el-select>
      <el-select v-model="assigned" multiple collapse-tags placeholder="允许接待的账号" style="width:360px" :disabled="!selectedStaff">
        <el-option v-for="account in rows" :key="account.id"
          :label="`${account.platform_name} · ${account.name}`" :value="account.id" />
      </el-select>
      <el-button type="primary" :disabled="!selectedStaff" @click="saveAccess">保存范围</el-button>
    </div>
  </el-card>
</template>
