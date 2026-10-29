<script setup lang="ts">
import { inject, onUnmounted, watchEffect } from 'vue';
import { PageHeadingKey } from '../pageHeading';
const props = defineProps<{ title: string; description?: string; eyebrow?: string; showTitle?: boolean }>();
const heading = inject(PageHeadingKey, null), owner = Symbol('page');
watchEffect(() => heading?.update(owner, { title: props.title, description: props.description || '' }));
onUnmounted(() => heading?.release(owner));
</script>
<template>
  <div v-if="!heading" class="pv-heading">
    <div><h2>{{title}}</h2><p v-if="description">{{description}}</p></div>
    <div class="pv-heading-actions"><slot/></div>
  </div>
</template>
