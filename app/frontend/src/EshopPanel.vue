<script setup lang="ts">
import { computed, defineAsyncComponent, provide } from "vue";
import ListPage from "./components/admin/ListPage.vue";
import EshopDialogs from "./views/eshop/EshopDialogs.vue";
import { useEshop } from "./views/eshop/useEshop";
const props = defineProps<{ view: string; token: string; readonly: boolean; accountId: number }>();
const emit = defineEmits<{
  error: [unknown];
  customerSession: [string, string, number];
}>();
const context = useEshop(props, (event, ...args) => {
  if (event === "error") emit("error", args[0]);
  else emit("customerSession", args[0], args[1], args[2]);
});
provide("eshop", context);
const {
  loading,
  dialog,
  titles,
  load,
  openProduct,
  openCustomer,
  list: { keyword, page, pageSize, total, query, reset },
} = context;
const pages = {
  customers: defineAsyncComponent(
    () => import("./views/eshop/CustomersPage.vue"),
  ),
  products: defineAsyncComponent(
    () => import("./views/eshop/ProductsPage.vue"),
  ),
  orders: defineAsyncComponent(() => import("./views/eshop/OrdersPage.vue")),
  payments: defineAsyncComponent(
    () => import("./views/eshop/PaymentsPage.vue"),
  ),
  shipments: defineAsyncComponent(
    () => import("./views/eshop/ShipmentsPage.vue"),
  ),
  refunds: defineAsyncComponent(() => import("./views/eshop/RefundsPage.vue")),
  inventory: defineAsyncComponent(
    () => import("./views/eshop/InventoryPage.vue"),
  ),
};
const currentPage = computed(() => pages[props.view as keyof typeof pages]);
defineExpose({ refresh: load });
</script>
<template>
  <ListPage
    :title="titles[view] || '电商管理'"
    description="本地电商模拟 · 支付、快递与退款均为虚构操作"
    :loading="loading"
    :total="total"
    v-model:page="page"
    v-model:page-size="pageSize"
  >
    <template #actions
      ><el-button
        v-if="!readonly && view === 'customers'"
        type="primary"
        @click="openCustomer()"
        >新增客户</el-button
      ><el-button
        v-if="!readonly && view === 'products'"
        type="primary"
        @click="openProduct()"
        >新增商品</el-button
      ><el-button
        v-if="!readonly && view === 'orders'"
        type="primary"
        @click="dialog = 'order'"
        >创建订单</el-button
      ></template
    >
    <template #filters
      ><el-input
        v-model="keyword"
        clearable
        placeholder="客户 / 商品 / 订单号等关键词"
        @keyup.enter="query"
      /><el-button type="primary" @click="query">查询</el-button
      ><el-button @click="reset">重置</el-button></template
    >
    <component :is="currentPage" :readonly="readonly" />
    <template #footer
      ><p class="list-note">
        当前分页和筛选基于已加载的数据：客户及商品最多 500 条，其余记录最近 200
        条。订单价格与收货信息保存下单快照。
      </p></template
    >
  </ListPage>
  <EshopDialogs />
</template>
