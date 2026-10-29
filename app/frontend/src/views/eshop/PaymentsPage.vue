<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
defineProps<{ readonly: boolean }>();
const {
  paymentLabels,
  label,
  list: { data },
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-table :data="data" border stripe row-key="id">
    <el-table-column prop="payment_no" label="支付单号" min-width="220" />
    <el-table-column prop="order_id" label="订单" min-width="200" />
    <el-table-column prop="customer" label="客户" />
    <el-table-column label="方式"
      ><template #default="{ row }">{{
        paymentLabels[row.method] || row.method
      }}</template></el-table-column
    >
    <el-table-column prop="amount" label="支付金额" />
    <el-table-column prop="refunded_amount" label="已退金额" />
    <el-table-column label="状态"
      ><template #default="{ row }">{{
        label(row.status)
      }}</template></el-table-column
    ></el-table
  >
</template>
