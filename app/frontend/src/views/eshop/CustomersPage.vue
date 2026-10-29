<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
defineProps<{ readonly: boolean }>();
const {
  openCustomer,
  busy,
  label,
  enterCustomer,
  list: { data },
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-table :data="data" border stripe row-key="id">
    <el-table-column prop="user_id" label="用户 ID" width="90" />
    <el-table-column prop="username" label="登录用户名" />
    <el-table-column prop="name" label="姓名" />
    <el-table-column prop="phone" label="电话" />
    <el-table-column prop="address" label="收货地址" min-width="220" />
    <el-table-column v-if="!readonly" label="操作" fixed="right" width="230"
      ><template #default="{ row }">
        <el-button
          link
          type="primary"
          :disabled="busy"
          @click="openCustomer(row)"
          >编辑</el-button
        >
        <el-button
          link
          type="primary"
          :disabled="busy"
          @click="enterCustomer(row)"
          >以此客户进入客服</el-button
        ></template
      ></el-table-column
    >
  </el-table>
</template>
