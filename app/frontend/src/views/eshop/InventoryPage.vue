<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
import { formatLocalDateTime } from "../../domain/datetime";
defineProps<{ readonly: boolean }>();
const {
  label,
  list: { data },
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-table :data="data" border stripe row-key="id">
    <el-table-column label="时间" min-width="190"><template #default="{ row }">{{ formatLocalDateTime(row.created_at) }}</template></el-table-column>
    <el-table-column prop="sku" label="SKU" min-width="160" />
    <el-table-column prop="delta" label="可售变动" />
    <el-table-column prop="reserved_delta" label="占用变动" />
    <el-table-column prop="available_after" label="变动后可售" />
    <el-table-column prop="reserved_after" label="变动后占用" />
    <el-table-column prop="reason" label="原因" min-width="180" />
    <el-table-column prop="actor" label="操作人" />
  </el-table>
</template>
