<script setup lang="ts">
import { computed } from 'vue';
import { ChatDotRound, Clock, Document, ShoppingBag, Reading, DataAnalysis, Setting, ArrowRight,
  ArrowDown, Search, Check, Plus, Picture, Close, Edit, MoreFilled, Refresh, Loading, ArrowLeft,
  InfoFilled, User, SwitchButton, CircleCheck, Warning, ChatLineRound, Shop, Position, CopyDocument,
  MagicStick, Connection, Sunny, UploadFilled } from '@element-plus/icons-vue';
const icons = { ChatDotRound, Clock, Document, ShoppingBag, Reading, DataAnalysis, Setting, ArrowRight,
  ArrowDown, Search, Check, Plus, Picture, Close, Edit, MoreFilled, Refresh, Loading, ArrowLeft,
  InfoFilled, User, SwitchButton, CircleCheck, Warning, ChatLineRound, Shop, Position, CopyDocument,
  MagicStick, Connection, Sunny, UploadFilled };
const props = defineProps<{ name: keyof typeof icons; spin?: boolean }>();
const icon = computed(() => icons[props.name]);
</script>
<template><span class="wb-icon" :class="{ 'is-spinning': spin }" aria-hidden="true"><component :is="icon" /></span></template>
