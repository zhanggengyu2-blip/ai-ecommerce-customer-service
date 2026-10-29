<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
defineProps<{ readonly: boolean }>();
const {
  busy,
  label,
  processRefund,
  list: { data },
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-table :data="data" border stripe row-key="id">
    <el-table-column prop="refund_no" label="退款单号" min-width="200" />
    <el-table-column prop="order_id" label="订单号" min-width="200" />
    <el-table-column prop="customer" label="客户" />
    <el-table-column prop="amount" label="退款金额" />
    <el-table-column prop="reason" label="原因" min-width="150" />
    <el-table-column label="状态" width="120"
      ><template #default="{ row }">{{
        label(row.status)
      }}</template></el-table-column
    >
    <el-table-column v-if="!readonly" label="操作" fixed="right" min-width="200"
      ><template #default="{ row }"
        ><template v-if="row.status === 'REQUESTED'">
          <el-button
            link
            type="primary"
            :disabled="busy"
            @click="processRefund(row, 'approve')"
            >批准</el-button
          >
          <el-button
            link
            type="danger"
            :disabled="busy"
            @click="processRefund(row, 'reject')"
            >驳回</el-button
          ></template
        >
        <el-button
          v-if="
            row.status === 'APPROVED' &&
            ['SHIPPED', 'DELIVERED'].includes(row.original_status)
          "
          link
          type="primary"
          :disabled="busy"
          @click="processRefund(row, 'receive')"
          >退货验收</el-button
        >
        <el-button
          v-if="
            row.status === 'RECEIVED' ||
            (row.status === 'APPROVED' && row.original_status === 'PAID')
          "
          link
          type="primary"
          :disabled="busy"
          @click="processRefund(row, 'complete')"
          >完成退款</el-button
        ></template
      ></el-table-column
    >
  </el-table>
</template>
