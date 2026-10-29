<script setup lang="ts">
defineProps<{ kind: 'trousers' | 'knit' | 'shirt'; small?: boolean; src?: string }>();
</script>
<template>
  <span class="wb-product-thumb" :class="{ small }" aria-hidden="true">
    <img v-if="src" :src="src" alt=""/><svg v-else-if="kind === 'trousers'" viewBox="0 0 64 80" fill="none">
      <path d="M17 6h30l3 62-14 2-4-43-4 43-14-2 3-62Z" fill="#30343b" />
      <path d="m17 6 30 0v5H17V6Z" fill="#21262d" />
      <path d="M32 11v16m-9-15-3 50m21-50 3 50M18 14l7 3m21-3-7 3" stroke="#555a61" stroke-width="1.2" />
      <path d="m15 67 13 1m8 0 13-1" stroke="#171d25" stroke-width="2" />
      <circle cx="32" cy="8.5" r="1" fill="#8e9298" />
    </svg>
    <svg v-else viewBox="0 0 80 80" fill="none">
      <path d="m26 11-12 9-9 23 12 6 8-16-3 36h36l-3-36 8 16 12-6-9-23-12-9-14 5-14-5Z" :fill="kind === 'knit' ? '#c4b39b' : '#b4c9db'" />
      <path d="M29 12c0 12 22 12 22 0" :stroke="kind === 'knit' ? '#a18e74' : '#819db7'" stroke-width="3" />
      <path v-if="kind === 'shirt'" d="m28 12 12 15 12-15M40 26v42m-17-3h34" stroke="#88a4bb" />
      <path v-else d="M26 29v34m6-34v34m6-34v34m6-34v34m6-34v34m-25 3h30" stroke="#b09c7f" stroke-width="1.2" opacity=".7" />
    </svg>
  </span>
</template>
