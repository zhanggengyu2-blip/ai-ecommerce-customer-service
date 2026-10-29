<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
defineProps<{ readonly: boolean }>();
const {
  busy,
  dialog,
  editing,
  label,
  tag,
  openProduct,
  toggleProduct,
  list: { data },
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-table :data="data" border stripe row-key="id">
    <el-table-column prop="sku" label="SKU" min-width="160" />
    <el-table-column prop="name" label="商品" min-width="150" />
    <el-table-column prop="price" label="价格（元）" width="110" />
    <el-table-column prop="inventory" label="可售库存" width="100" />
    <el-table-column prop="reserved" label="占用库存" width="100" />
    <el-table-column label="状态" width="100"
      ><template #default="{ row }">
        <el-tag :type="tag(row.status)">{{
          label(row.status)
        }}</el-tag></template
      ></el-table-column
    >
    <el-table-column v-if="!readonly" label="操作" fixed="right" min-width="240"
      ><template #default="{ row }">
        <el-button
          link
          type="primary"
          :disabled="busy"
          @click="openProduct(row)"
          >编辑</el-button
        >
        <el-button
          link
          type="primary"
          :disabled="busy"
          @click="toggleProduct(row)"
          >{{ row.status === "ON_SALE" ? "下架" : "上架" }}</el-button
        >
        <el-button
          link
          type="primary"
          :disabled="busy"
          @click="
            editing = row;
            dialog = 'stock';
          "
          >调整库存</el-button
        ></template
      ></el-table-column
    >
  </el-table>
</template>
