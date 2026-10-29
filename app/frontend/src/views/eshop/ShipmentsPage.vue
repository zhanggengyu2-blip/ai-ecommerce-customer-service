<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
import { formatLocalDateTime } from "../../domain/datetime";
defineProps<{ readonly: boolean }>();
const {
  orders,
  busy,
  label,
  updateLogistics,
  list: { data },
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-table :data="data" border stripe row-key="id">
    <el-table-column type="expand"
      ><template #default="{ row }">
        <el-timeline class="shipment-timeline">
          <el-timeline-item
            v-for="(event, index) in row.events"
            :key="index"
            :timestamp="formatLocalDateTime(event.time)"
            >{{ label(event.status) }} ·
            {{ event.description }}</el-timeline-item
          ></el-timeline
        ></template
      ></el-table-column
    >
    <el-table-column prop="order_id" label="订单号" min-width="200" />
    <el-table-column prop="customer" label="客户" />
    <el-table-column prop="carrier" label="承运商" />
    <el-table-column prop="tracking_number" label="运单号" min-width="180" />
    <el-table-column label="状态"
      ><template #default="{ row }">{{
        label(row.status)
      }}</template></el-table-column
    >
    <el-table-column v-if="!readonly" label="操作" fixed="right" min-width="190"
      ><template #default="{ row }"
        ><template
          v-if="
            row.status !== 'DELIVERED' &&
            orders.some(
              (o) => o.order_id === row.order_id && o.status === 'SHIPPED',
            )
          "
        >
          <el-button
            v-if="row.status === 'IN_TRANSIT'"
            link
            type="primary"
            :disabled="busy"
            @click="updateLogistics(row, 'OUT_FOR_DELIVERY')"
            >模拟派送</el-button
          >
          <el-button
            link
            type="primary"
            :disabled="busy"
            @click="updateLogistics(row, 'DELIVERED')"
            >模拟签收</el-button
          ></template
        ></template
      ></el-table-column
    >
  </el-table>
</template>
