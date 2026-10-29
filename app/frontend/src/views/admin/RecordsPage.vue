<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api } from "../../api";
import ListPage from "../../components/admin/ListPage.vue";
import { useLocalList } from "../../composables/useLocalList";
import type { AdminProps } from "../../domain/roles";
import { formatLocalDateTime } from "../../domain/datetime";
const props = defineProps<AdminProps>(),
  emit = defineEmits<{ error: [unknown] }>();
type RecordRow = Record<string, unknown>;
const rows = ref<RecordRow[]>([]),
  loading = ref(false);
const { keyword, page, pageSize, data, total, query, reset } =
  useLocalList(rows);
const definitions: Record<
  string,
  {
    title: string;
    endpoint: string;
    columns: {
      prop: string;
      label: string;
      width?: number;
      minWidth?: number;
    }[];
    limit: string;
  }
> = {
  audit: {
    title: "审计日志",
    endpoint: "audit",
    limit: "最近 100 条",
    columns: [
      { prop: "created_at", label: "时间", width: 190 },
      { prop: "actor", label: "操作人", width: 140 },
      { prop: "action", label: "动作", width: 180 },
      { prop: "target", label: "对象", minWidth: 200 },
    ],
  },
  feedback: {
    title: "用户反馈",
    endpoint: "feedback",
    limit: "最近 200 条",
    columns: [
      { prop: "conversation_id", label: "会话", width: 90 },
      { prop: "rating", label: "评价", width: 90 },
      { prop: "reason", label: "原因", width: 150 },
      { prop: "answer", label: "对应回答", minWidth: 350 },
    ],
  },
  popular: {
    title: "热门问题",
    endpoint: "popular-questions",
    limit: "按问题原文统计，最多 50 项",
    columns: [
      { prop: "query", label: "问题", minWidth: 350 },
      { prop: "count", label: "次数", width: 100 },
    ],
  },
};
const definition = computed(
  () => definitions[props.page]!,
);
async function load() {
  loading.value = true;
  try {
    const result = await api<RecordRow[]>(
      `/api/admin/${definition.value.endpoint}${props.accountId && props.page !== 'audit' ? `?account_id=${props.accountId}` : ''}`,
      "GET",
      undefined,
      props.token,
    );
    rows.value = result;
  } catch (e) {
    emit("error", e);
  } finally {
    loading.value = false;
  }
}
watch([() => props.accountId, () => props.page], load, { immediate: true });
</script>
<template>
  <ListPage
    :title="definition.title"
    :loading="loading"
    :total="total"
    v-model:page="page"
    v-model:page-size="pageSize"
    ><template #filters
      ><el-input
        v-model="keyword"
        clearable
        placeholder="输入关键词"
        @keyup.enter="query"
      /><el-button type="primary" @click="query">查询</el-button
      ><el-button @click="reset">重置</el-button></template
    ><el-table :data="data" border stripe
      ><el-table-column
        v-for="column in definition.columns"
        :key="column.prop"
        :prop="column.prop"
        :label="column.label"
        :width="column.width"
        :min-width="column.minWidth"
        show-overflow-tooltip
        ><template #default="{ row }">{{
          column.prop === "created_at"
            ? formatLocalDateTime(row.created_at as string)
            : column.prop === "rating"
            ? Number(row.rating) > 0
              ? "满意"
              : "不满意"
            : (row[column.prop] ?? "—")
        }}</template></el-table-column
      ></el-table
    ><template #footer
      ><p class="list-note">
        {{ definition.limit }}；查询和分页作用于已加载记录。
      </p></template
    ></ListPage
  >
</template>
