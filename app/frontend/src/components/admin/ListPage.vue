<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string;
    description?: string;
    loading?: boolean;
    total: number;
    page: number;
    pageSize: number;
  }>(),
  { loading: false },
);
const emit = defineEmits<{
  "update:page": [number];
  "update:pageSize": [number];
}>();
</script>

<template>
  <el-card class="list-page" shadow="never">
    <template #header>
      <div class="list-header">
        <div>
          <h2>{{ title }}</h2>
          <p v-if="description">{{ description }}</p>
        </div>
        <div class="list-actions"><slot name="actions" /></div>
      </div>
    </template>
    <div v-if="$slots.filters" class="query-bar"><slot name="filters" /></div>
    <div v-loading="loading" class="list-body"><slot /></div>
    <div class="pagination-bar">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @update:current-page="emit('update:page', $event)"
        @update:page-size="emit('update:pageSize', $event)"
      />
    </div>
    <slot name="footer" />
  </el-card>
</template>
