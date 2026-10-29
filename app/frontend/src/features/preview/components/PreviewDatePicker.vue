<script setup lang="ts">
import { ref } from 'vue';
defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<{
  modelValue: string; type?: 'date' | 'datetime'; min?: string; max?: string;
}>(), { type: 'date' });
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const picker = ref<{ handleOpen: () => void } | null>(null);
function open(event: MouseEvent) {
  if (!(event.target as HTMLElement).closest('.clear-icon')) picker.value?.handleOpen();
}
function disabledDate(date: Date) {
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  return !!((props.min && day < new Date(`${props.min.slice(0, 10)}T00:00:00`).getTime())
    || (props.max && day > new Date(`${props.max.slice(0, 10)}T00:00:00`).getTime()));
}
</script>
<template>
  <div class="pv-date-control" @mousedown.capture="open">
    <el-date-picker ref="picker" v-bind="$attrs" class="pv-date-input" :type="type"
      :model-value="modelValue || undefined" :editable="false" clearable
      :format="type === 'date' ? 'YYYY/MM/DD' : 'YYYY/MM/DD HH:mm'"
      :value-format="type === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DDTHH:mm'"
      :placeholder="type === 'date' ? '选择日期' : '选择日期和时间'" :disabled-date="disabledDate"
      @update:model-value="emit('update:modelValue', $event || '')"/>
  </div>
</template>
