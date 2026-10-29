<script setup lang="ts">
import { onUnmounted, ref } from 'vue';
import { createApi, STAFF_TOKEN } from '../../features/live/api';
import LiveWorkspace from './LiveWorkspace.vue';
import '../../features/workbench/workbench.css';
import '../../features/preview/color-theme.css';
import './live.css';
const authenticated = ref(!!sessionStorage.getItem(STAFF_TOKEN));
const account = ref(''), password = ref(''), error = ref(''), busy = ref(false);
const api = createApi(() => null);
async function login() {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try {
    const result = await api<{access_token: string}>('/api/auth/login', { account: account.value, password: password.value });
    sessionStorage.setItem(STAFF_TOKEN, result.access_token); password.value = ''; authenticated.value = true;
  } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; }
}
function leave(message = '') { sessionStorage.removeItem(STAFF_TOKEN); authenticated.value = false; error.value = message; }
function expired(event: Event) { leave((event as CustomEvent<string>).detail); }
window.addEventListener('foundation-session-expired', expired);
onUnmounted(() => window.removeEventListener('foundation-session-expired', expired));
</script>
<template>
  <LiveWorkspace v-if="authenticated" @logout="leave()" />
  <div v-else class="live-login"><form class="live-login-card" @submit.prevent="login"><div class="live-symbol">禾</div><h1>登录客服工作台</h1><p>每次沟通，都有记录可循。</p><label>客服账号<input v-model="account" autocomplete="username" required maxlength="120" placeholder="请输入客服账号" /></label><label>密码<input v-model="password" type="password" autocomplete="current-password" required placeholder="请输入密码" /></label><p v-if="error" role="alert" class="live-error">{{error}}</p><button class="wb-btn primary" :disabled="busy">{{busy?'正在登录…':'登录'}}</button></form></div>
</template>
