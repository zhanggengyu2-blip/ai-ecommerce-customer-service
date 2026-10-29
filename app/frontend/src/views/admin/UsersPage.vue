<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import { ElMessageBox } from "element-plus/es/components/message-box/index.mjs";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";
import type { FormInstance, FormRules } from "element-plus/es/components/form/index.mjs";
import { api } from "../../api";
import ListPage from "../../components/admin/ListPage.vue";
import { formatLocalDateTime } from "../../domain/datetime";
import {
  roleRows,
  staffRoles,
  type UnifiedUser,
  type AdminProps,
} from "../../domain/roles";

const props = defineProps<AdminProps>();
const emit = defineEmits<{ error: [unknown] }>();
const localTime = formatLocalDateTime;
const rows = ref<UnifiedUser[]>([]),
  total = ref(0),
  loading = ref(false),
  saving = ref(false);
const page = ref(1),
  pageSize = ref(20);
const filters = reactive({ keyword: "", user_type: "", role: "", active: "" });
let applied = { ...filters },
  generation = 0;
async function load() {
  const request = ++generation;
  loading.value = true;
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      page_size: String(pageSize.value),
    });
    Object.entries(applied).forEach(([key, value]) => {
      if (value !== "") params.set(key, value);
    });
    const result = await api<{ items: UnifiedUser[]; total: number }>(
      `/api/admin/users/page?${params}`,
      "GET",
      undefined,
      props.token,
    );
    if (request === generation) {
      rows.value = result.items;
      total.value = result.total;
      const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value));
      if (page.value > lastPage) page.value = lastPage;
    }
  } catch (e) {
    if (request === generation) emit("error", e);
  } finally {
    if (request === generation) loading.value = false;
  }
}
function query() {
  applied = { ...filters };
  if (page.value === 1) load();
  else page.value = 1;
}
function reset() {
  Object.assign(filters, { keyword: "", user_type: "", role: "", active: "" });
  query();
}
watch(page, load);
watch(pageSize, () => {
  if (page.value === 1) load();
  else page.value = 1;
});
const visible = ref(false),
  editing = ref<UnifiedUser | null>(null),
  formRef = ref<FormInstance>();
const form = reactive({
  username: "",
  display_name: "",
  user_type: "B",
  role: "CUSTOMER_SERVICE",
  password: "",
  active: true,
});
const rules: FormRules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { max: 128, message: "最多 128 个字符", trigger: "blur" },
  ],
  display_name: [{ required: true, message: "请输入姓名", trigger: "blur" }],
  password: [
    {
      validator: (_rule, value, callback) => {
        if (editing.value && !value) callback();
        else if (!value || value.length < 12 || value.length > 128)
          callback(new Error("密码须为 12 至 128 位"));
        else callback();
      },
      trigger: "blur",
    },
  ],
};
function open(row?: UnifiedUser) {
  editing.value = row || null;
  Object.assign(
    form,
    row
      ? { ...row, password: "" }
      : {
          username: "",
          display_name: "",
          user_type: "B",
          role: "CUSTOMER_SERVICE",
          password: "",
          active: true,
        },
  );
  visible.value = true;
  formRef.value?.clearValidate();
}
function changeType(type: string) {
  form.role = type === "C" ? "CUSTOMER" : "CUSTOMER_SERVICE";
}
async function save() {
  if (saving.value || !(await formRef.value?.validate().catch(() => false)))
    return;
  saving.value = true;
  try {
    if (editing.value) {
      await api(
        `/api/admin/users/${editing.value.id}`,
        "PATCH",
        {
          display_name: form.display_name,
          active: form.active,
          ...(editing.value.kind === "STAFF" ? { role: form.role } : {}),
          ...(form.password ? { password: form.password } : {}),
        },
        props.token,
      );
    } else {
      await api(
        "/api/admin/users",
        "POST",
        {
          username: form.username.trim(),
          display_name: form.display_name,
          user_type: form.user_type,
          role: form.role,
          password: form.password,
        },
        props.token,
      );
    }
    ElMessage.success(editing.value ? "用户已更新" : "用户已创建");
    visible.value = false;
    form.password = "";
    await load();
  } catch (e) {
    emit("error", e);
  } finally {
    saving.value = false;
  }
}
async function toggle(row: UnifiedUser) {
  try {
    await ElMessageBox.confirm(
      `确认${row.active ? "停用" : "启用"} ${row.display_name || row.username}？`,
      "用户状态",
      { type: "warning", confirmButtonText: "确认", cancelButtonText: "取消" },
    );
    await api(
      `/api/admin/users/${row.id}`,
      "PATCH",
      { active: !row.active },
      props.token,
    );
    ElMessage.success("状态已更新");
    await load();
  } catch (e) {
    if (e !== "cancel" && e !== "close") emit("error", e);
  }
}
onMounted(load);
defineExpose({ refresh: load });
</script>

<template>
  <ListPage
    title="统一用户"
    description="客户、游客与商家统一管理；客户收货资料在电商管理的客户管理中维护。"
    :loading="loading"
    :total="total"
    v-model:page="page"
    v-model:page-size="pageSize"
  >
    <template #actions
      ><el-button type="primary" @click="open()">新增用户</el-button></template
    >
    <template #filters>
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="用户名 / 姓名 / 邮箱"
        @keyup.enter="query"
      />
      <el-select v-model="filters.user_type" clearable placeholder="用户类型"
        ><el-option label="客户端" value="C" /><el-option
          label="商户端"
          value="B"
      /></el-select>
      <el-select v-model="filters.role" clearable placeholder="角色"
        ><el-option
          v-for="r in roleRows"
          :key="r.role"
          :value="r.role"
          :label="r.name"
      /></el-select>
      <el-select v-model="filters.active" clearable placeholder="启用状态"
        ><el-option label="启用" value="true" /><el-option
          label="停用"
          value="false"
      /></el-select>
      <el-button type="primary" @click="query">查询</el-button
      ><el-button @click="reset">重置</el-button>
    </template>
    <el-table
      :data="rows"
      row-key="id"
      border
      stripe
      empty-text="暂无符合条件的用户"
    >
      <el-table-column prop="id" label="ID" width="75" />
      <el-table-column
        prop="username"
        label="用户名"
        min-width="210"
        show-overflow-tooltip
      />
      <el-table-column
        prop="display_name"
        label="姓名"
        min-width="140"
        show-overflow-tooltip
      />
      <el-table-column label="类型" width="125"
        ><template #default="{ row }"
          ><el-tag :type="row.user_type === 'B' ? 'primary' : 'info'">{{
            row.user_type === "B" ? "商户端" : "客户端"
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="角色" width="130"
        ><template #default="{ row }">{{
          roleRows.find((r) => r.role === row.role)?.name || row.role
        }}</template></el-table-column
      >
      <el-table-column label="状态" width="90"
        ><template #default="{ row }"
          ><el-tag :type="row.active ? 'success' : 'info'">{{
            row.active ? "启用" : "停用"
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="创建时间" min-width="170"><template #default="{ row }">{{ localTime(row.created_at) }}</template></el-table-column>
      <el-table-column label="修改时间" min-width="170"><template #default="{ row }">{{ localTime(row.updated_at) }}</template></el-table-column>
      <el-table-column label="操作" fixed="right" width="155"
        ><template #default="{ row }"
          ><template v-if="row.role !== 'SUPER_ADMIN'"
            ><el-button type="primary" link @click="open(row)">编辑</el-button
            ><el-button
              :type="row.active ? 'danger' : 'primary'"
              link
              :disabled="row.id === currentUserId && row.active"
              @click="toggle(row)"
              >{{ row.active ? "停用" : "启用" }}</el-button
            ></template
          ><span v-else class="muted">系统管理员</span></template
        ></el-table-column
      >
    </el-table>
  </ListPage>
  <el-dialog
    v-model="visible"
    :title="editing ? '编辑用户' : '新增用户'"
    width="560px"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="form.password = ''"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="95px"
      @submit.prevent="save"
    >
      <el-form-item label="用户名" prop="username"
        ><el-input
          v-model="form.username"
          :disabled="!!editing"
          maxlength="128"
          autocomplete="off"
      /></el-form-item>
      <el-form-item label="姓名" prop="display_name"
        ><el-input v-model="form.display_name" maxlength="128"
      /></el-form-item>
      <el-form-item label="用户类型"
        ><el-radio-group
          v-model="form.user_type"
          :disabled="!!editing"
          @change="changeType(String($event))"
          ><el-radio-button value="B">商户端</el-radio-button
          ><el-radio-button value="C">客户端</el-radio-button></el-radio-group
        ></el-form-item
      >
      <el-form-item label="角色"
        ><el-select v-if="form.user_type === 'B'" v-model="form.role"
          ><el-option
            v-for="r in staffRoles"
            :key="r.role"
            :value="r.role"
            :label="r.name" /></el-select
        ><el-tag v-else>{{
          editing?.kind === "GUEST" ? "游客" : "客户"
        }}</el-tag></el-form-item
      >
      <el-form-item
        v-if="editing?.kind !== 'GUEST'"
        :label="editing ? '新密码' : '登录密码'"
        prop="password"
        ><el-input
          v-model="form.password"
          type="password"
          show-password
          autocomplete="new-password"
          :placeholder="editing ? '留空则保留原密码' : '至少 12 位'"
          maxlength="128"
      /></el-form-item>
      <el-form-item v-if="editing" label="启用状态"
        ><el-switch
          v-model="form.active"
          :disabled="editing.id === currentUserId"
      /></el-form-item>
    </el-form>
    <template #footer
      ><el-button :disabled="saving" @click="visible = false">取消</el-button
      ><el-button type="primary" :loading="saving" @click="save"
        >保存</el-button
      ></template
    >
  </el-dialog>
</template>
