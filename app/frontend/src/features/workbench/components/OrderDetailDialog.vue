<script setup lang="ts">
import type { WorkbenchOrder } from '../types';
import { dateOf, money } from '../types';
import ProductThumbnail from './ProductThumbnail.vue';
defineProps<{ modelValue: boolean; order: WorkbenchOrder | null }>();
defineEmits<{ 'update:modelValue': [value: boolean] }>();
</script>
<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="订单详情" width="580px" class="wb-dialog" align-center>
    <template v-if="order">
      <div class="wb-detail-title"><span>{{ order.number }}</span><span class="wb-status order-status">{{ order.status }}</span></div>
      <div class="wb-detail-product"><ProductThumbnail :kind="order.thumbnail" :src="order.imageUrl" /><div><strong>{{ order.product }}</strong><p>{{ order.variant }} × {{ order.quantity }}</p></div><b>{{ money(order.amount) }}</b></div>
      <h4 class="wb-section-label">订单信息</h4>
      <dl class="wb-detail-grid"><dt>订单金额</dt><dd>{{ money(order.amount) }}</dd><dt>支付时间</dt><dd>{{ dateOf(order.paidAt) }}</dd><dt>商品数量</dt><dd>{{ order.quantity }} 件</dd></dl>
      <h4 class="wb-section-label">收货与物流</h4>
      <dl class="wb-detail-grid"><dt>收件人</dt><dd>{{ order.receiver }}</dd><dt>收货地址</dt><dd>{{ order.address }}</dd><dt>承运方</dt><dd>{{ order.carrier }}</dd><dt>物流单号</dt><dd>{{ order.tracking }}</dd></dl>
    </template>
    <template #footer><button class="wb-btn" @click="$emit('update:modelValue', false)">关闭</button></template>
  </el-dialog>
</template>
