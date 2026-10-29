<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import type { TicketInput, TicketType, WorkbenchConversation, WorkbenchOrder, WorkbenchTicket } from '../types';
import { ticketTypeLabels } from '../types';
import Icon from './WorkbenchIcon.vue';
const props = defineProps<{
  modelValue: boolean; conversation: WorkbenchConversation | null; order: WorkbenchOrder | null;
  ticket: WorkbenchTicket | null; save: (input: TicketInput, existing?: WorkbenchTicket) => Promise<WorkbenchTicket>;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; saved: [ticket: WorkbenchTicket] }>();
const form = reactive({ types: [] as TicketType[], description: '', refundAmount: '', exchangeTarget: '', newAddress: '' });
const error = ref(''), saving = ref(false);
const hasRefund = computed(() => form.types.includes('REFUND_ONLY') || form.types.includes('RETURN_REFUND'));
watch(() => props.modelValue, open => {
  if (!open) return;
  const ticket = props.ticket;
  Object.assign(form, { types: ticket ? [...ticket.types] : [], description: ticket?.description || '',
    refundAmount: ticket?.refundAmount || '', exchangeTarget: ticket?.exchangeTarget || '', newAddress: ticket?.newAddress || '' });
  error.value = '';
});
async function submit() {
  if (saving.value || !props.order || !props.conversation) return;
  if (!form.types.length) { error.value = '请至少选择一种诉求类型。'; return; }
  if (!form.description.trim()) { error.value = '请填写这次需要处理的具体诉求。'; return; }
  saving.value = true; error.value = '';
  try {
    const result = await props.save({ conversationId: props.conversation.id, orderId: props.order.id,
      types: [...form.types], description: form.description.trim(), refundAmount: hasRefund.value ? form.refundAmount.trim() : '',
      exchangeTarget: form.types.includes('EXCHANGE') ? form.exchangeTarget.trim() : '',
      newAddress: form.types.includes('CHANGE_ADDRESS') ? form.newAddress.trim() : '' }, props.ticket || undefined);
    emit('saved', result); emit('update:modelValue', false);
  } catch (err) { error.value = (err as Error).message; }
  finally { saving.value = false; }
}
</script>
<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" :title="ticket ? '查看与编辑工单' : '新增客服工单'" width="600px" class="wb-dialog wb-ticket-dialog" align-center :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving">
    <form id="wb-ticket-form" @submit.prevent="submit" v-if="conversation && order">
      <div class="wb-locked-context"><Icon name="InfoFilled" /><div><strong>已关联当前客户、会话与订单</strong><span>{{ conversation.customer }} · 会话 #{{ conversation.id }}<br />{{ order.number }} · {{ order.product }}</span></div><span v-if="ticket" class="wb-status" :class="ticket.completion === 'DONE' ? 'closed' : 'waiting'">{{ ticket.completion === 'DONE' ? '已完成' : '待完成' }}</span></div>
      <fieldset class="wb-fieldset"><legend>诉求类型 <em>*</em><small>同一订单可选择多种诉求</small></legend><div class="wb-ticket-types"><label v-for="(label, type) in ticketTypeLabels" :key="type" :class="{ selected: form.types.includes(type) }"><input v-model="form.types" type="checkbox" :value="type" />{{ label }}</label></div></fieldset>
      <label class="wb-form-field">诉求说明 <em>*</em><textarea v-model="form.description" rows="4" maxlength="1000" placeholder="例如：订单内 2 件长裤，1 件退货退款，另一件换成 L 码。" aria-label="诉求说明" /><small class="wb-input-count">{{ form.description.length }} / 1000</small></label>
      <label v-if="hasRefund" class="wb-form-field">申请金额 <small>选填，部分退款在这里记录</small><div class="wb-money-input"><span>¥</span><input v-model="form.refundAmount" inputmode="decimal" placeholder="例如 129.00" aria-label="申请金额" /></div></label>
      <label v-if="form.types.includes('EXCHANGE')" class="wb-form-field">换货目标 <small>选填</small><input v-model="form.exchangeTarget" maxlength="200" placeholder="例如：同款黑色 L 码" aria-label="换货目标" /></label>
      <label v-if="form.types.includes('CHANGE_ADDRESS')" class="wb-form-field">新收货信息 <small>选填</small><textarea v-model="form.newAddress" rows="2" maxlength="500" placeholder="记录协商后的收件人、联系电话和完整地址" aria-label="新收货信息" /></label>
      <p class="wb-form-note">工单用于记录诉求，保存不会直接修改订单、退款或物流。</p>
      <p v-if="error" class="wb-form-error" role="alert"><Icon name="Warning" />{{ error }}</p>
    </form>
    <template #footer><button class="wb-btn" :disabled="saving" @click="$emit('update:modelValue', false)">取消</button><button class="wb-btn primary" type="submit" form="wb-ticket-form" :disabled="saving"><Icon v-if="saving" name="Loading" spin />{{ saving ? '正在保存' : ticket ? '保存修改' : '创建工单' }}</button></template>
  </el-dialog>
</template>
