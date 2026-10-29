<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
defineProps<{ readonly: boolean }>();
const {
  busy,
  dialog,
  selected,
  label,
  tag,
  openOrderAction,
  cancelOrder,
  refund,
  list: { data },
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-table :data="data" border stripe row-key="id">
    <el-table-column prop="order_id" label="订单号" min-width="200" />
    <el-table-column prop="user_id" label="归属用户 ID" width="110" />
    <el-table-column prop="customer_username" label="客户" width="130" />
    <el-table-column prop="product_sku" label="SKU" min-width="140" />
    <el-table-column prop="quantity" label="数量" width="65" />
    <el-table-column prop="amount" label="金额（元）" width="100" />
    <el-table-column label="状态" min-width="145"
      ><template #default="{ row }">
        <el-tag :type="tag(row.status)">{{
          label(row.status)
        }}</el-tag></template
      ></el-table-column
    >
    <el-table-column label="操作" fixed="right" min-width="250"
      ><template #default="{ row }">
        <el-button
          link
          type="primary"
          @click="
            selected = row;
            dialog = 'detail';
          "
          >详情</el-button
        ><template v-if="!readonly">
          <el-button
            v-if="row.status === 'UNPAID'"
            link
            type="primary"
            :disabled="busy"
            @click="openOrderAction(row, 'pay')"
            >支付</el-button
          >
          <el-button
            v-if="row.status === 'PAID' && row.refund_status === 'NONE'"
            link
            type="primary"
            :disabled="busy"
            @click="openOrderAction(row, 'ship')"
            >发货</el-button
          >
          <el-button
            v-if="
              ['PAID', 'SHIPPED', 'DELIVERED'].includes(row.status) &&
              row.refund_status === 'NONE'
            "
            link
            type="warning"
            :disabled="busy"
            @click="refund(row)"
            >申请退款</el-button
          >
          <el-button
            v-if="
              ['UNPAID', 'PAID'].includes(row.status) &&
              row.refund_status === 'NONE'
            "
            link
            type="danger"
            :disabled="busy"
            @click="cancelOrder(row)"
            >取消订单</el-button
          ></template
        ></template
      ></el-table-column
    >
  </el-table>
</template>
