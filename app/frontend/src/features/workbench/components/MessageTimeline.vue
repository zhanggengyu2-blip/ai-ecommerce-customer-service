<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import type { WorkbenchMessage, WorkbenchOrder } from '../types';
import { money, timeOf } from '../types';
import ProductThumbnail from './ProductThumbnail.vue';
import Icon from './WorkbenchIcon.vue';
const props = defineProps<{ messages: WorkbenchMessage[]; orders: WorkbenchOrder[]; customer: string; tone?: string; history?: boolean; active?: boolean }>();
defineEmits<{ order: [order: WorkbenchOrder]; image: [url: string] }>();
const container = ref<HTMLElement | null>(null);
const lastCount = computed(() => `${props.customer}:${props.messages.at(-1)?.id}:${props.messages.length}`);
watch([lastCount, () => props.active], async () => { await nextTick(); if (container.value) container.value.scrollTop = container.value.scrollHeight; }, { immediate: true });
const orderFor = (id?: number) => props.orders.find(o => o.id === id);
</script>
<template>
  <div ref="container" class="wb-timeline" :class="{ 'is-history': history }" role="log" :aria-label="`${customer}的会话消息`" aria-live="polite" aria-relevant="additions">
    <div v-if="!history" class="wb-timeline-date">今天 {{ messages[0] ? timeOf(messages[0].createdAt) : '' }}</div>
    <template v-for="message in messages" :key="message.id">
      <div v-if="message.kind === 'divider'" class="wb-stage-divider"><span>{{ message.content }}</span></div>
      <article v-else class="wb-message" :class="[message.sender, { outgoing: message.sender !== 'customer' }]">
        <span class="wb-avatar wb-message-avatar" :class="message.sender === 'customer' ? tone : 'blue'">
          <Icon v-if="message.sender === 'ai'" name="Connection" /><template v-else>{{ message.sender === 'customer' ? customer.slice(0, 1) : message.name.replace('客服', '').slice(0, 1) }}</template>
        </span>
        <div class="wb-message-main">
          <div class="wb-message-meta"><span>{{ message.name }}</span><time>{{ timeOf(message.createdAt) }}</time></div>
          <button v-if="message.kind === 'order' && orderFor(message.orderId)" class="wb-order-message" @click="$emit('order', orderFor(message.orderId)!)" aria-label="查看消息中的订单详情">
            <ProductThumbnail :kind="orderFor(message.orderId)!.thumbnail" :src="orderFor(message.orderId)!.imageUrl" />
            <span><strong>{{ orderFor(message.orderId)!.product }}</strong><small>{{ orderFor(message.orderId)!.variant }} × {{ orderFor(message.orderId)!.quantity }}</small><b>{{ money(orderFor(message.orderId)!.amount) }}</b><small class="order-number">订单号：{{ orderFor(message.orderId)!.number }}</small></span>
            <Icon name="ArrowRight" />
          </button>
          <button v-else-if="message.kind === 'image'" class="wb-image-message" @click="$emit('image', message.imageUrl!)" aria-label="放大查看图片"><img :src="message.imageUrl" alt="会话图片" /></button>
          <div v-else class="wb-message-bubble">{{ message.content }}</div>
          <details v-if="message.citations?.length" class="live-sources"><summary>知识来源 · {{message.citations.length}} 个段落</summary><div v-for="(source,index) in message.citations" :key="index"><strong>{{source.document_title}} · v{{source.version}}</strong><p>{{source.content}}</p></div></details>
          <a v-if="message.traceId && !history" class="wb-text-button live-trace-link" :href="`?mode=live#traces/${message.traceId}`">查看调用记录</a>
        </div>
      </article>
    </template>
    <div v-if="!messages.length" class="wb-chat-start"><Icon name="ChatLineRound" /><p>本次会话已准备好</p><small>发送一条消息，继续与客户沟通</small></div>
  </div>
</template>
