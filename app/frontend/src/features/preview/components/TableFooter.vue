<script setup lang="ts">
import { watch } from 'vue';
const props=defineProps<{ total: number; page: number; size?: number }>();
const emit=defineEmits<{ 'update:page': [page: number] }>();
watch(()=>[props.total,props.page,props.size],()=>{const max=Math.max(1,Math.ceil(props.total/(props.size||8)));if(props.page>max)emit('update:page',max);});
</script>
<template><div class="pv-table-footer"><span>共 {{ total }} 条记录</span><div><button class="pv-page-button" :disabled="page <= 1" aria-label="上一页" @click="$emit('update:page', page-1)">‹</button><span>{{ page }} / {{ Math.max(1, Math.ceil(total / (size || 8))) }}</span><button class="pv-page-button" :disabled="page >= Math.ceil(total / (size || 8))" aria-label="下一页" @click="$emit('update:page', page+1)">›</button></div></div></template>
