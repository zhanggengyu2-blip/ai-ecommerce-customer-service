<script setup lang="ts">
import { computed, onUnmounted, provide, ref, shallowRef, watch } from 'vue';
import { useWorkbench, WorkbenchKey } from '../../features/workbench/useWorkbench';
import { createPreviewStore, PreviewKey, navigate } from '../../features/preview/usePreviewStore';
import Icon from '../../features/workbench/components/WorkbenchIcon.vue';
import WorkbenchPage from '../support/WorkbenchPage.vue';
import TodosPage from './TodosPage.vue';
import HistoryPage from './HistoryPage.vue';
import CommercePage from './CommercePage.vue';
import ModelsPage from './ModelsPage.vue';
import KnowledgePage from './KnowledgePage.vue';
import RecallPage from './RecallPage.vue';
import PromptsPage from './PromptsPage.vue';
import AnalysisPage from './AnalysisPage.vue';
import SettingsPage from './SettingsPage.vue';
import ReplyRoutesPage from './ReplyRoutesPage.vue';
import ConversationRecordDrawer from '../../features/preview/components/ConversationRecordDrawer.vue';
import ReplyTraceDialog from '../../features/preview/components/ReplyTraceDialog.vue';
import { PageHeadingKey, type PageHeadingData } from '../../features/preview/pageHeading';
import '../../features/workbench/workbench.css';
import '../../features/preview/preview.css';
import '../../features/preview/color-theme.css';
const wb=useWorkbench();provide(WorkbenchKey,wb);const s=createPreviewStore(wb);provide(PreviewKey,s);
const heading=shallowRef<(PageHeadingData & {owner:symbol})|null>(null);
provide(PageHeadingKey, {
  update(owner,data){heading.value={owner,...data};},
  release(owner){if(heading.value?.owner===owner)heading.value=null;},
});
const support=[{id:'workbench',title:'会话工作台',icon:'ChatDotRound'},{id:'todos',title:'待办事项',icon:'Clock'},{id:'history',title:'历史会话记录',icon:'Document'}] as const;
const groups=[{id:'commerce',title:'电商管理',icon:'ShoppingBag',children:[{id:'customers',title:'客户管理'},{id:'products',title:'商品管理'},{id:'orders',title:'订单管理'},{id:'payments',title:'支付记录'},{id:'shipments',title:'物流管理'},{id:'refunds',title:'退款售后'},{id:'inventory',title:'库存流水'}]},{id:'knowledge',title:'AI 与知识',icon:'Reading',children:[{id:'models',title:'AI 模型配置'},{id:'categories',title:'知识库'},{id:'documents',title:'客服知识'},{id:'chunks',title:'知识切片'},{id:'recall',title:'召回测试'},{id:'prompts',title:'Prompt 模板'}]},{id:'analysis',title:'分析与反馈',icon:'DataAnalysis',children:[{id:'dashboard',title:'数据分析'},{id:'traces',title:'回复路由记录'},{id:'feedback',title:'回答反馈'},{id:'followups',title:'待跟进问题'}]}] as const;
const valid=new Set(['support/workbench','support/todos','support/history',...groups.flatMap(g=>g.children.map(c=>`${g.id}/${c.id}`)),...['shop','accounts','rules','greeting','retrieval'].map(v=>`settings/${v}`)]);
const hash=ref(window.location.hash),mobileNav=ref(false),expanded=ref('');
function hashChanged(){hash.value=window.location.hash;mobileNav.value=false;}
function closeNav(event:KeyboardEvent){if(event.key==='Escape')mobileNav.value=false;}
window.addEventListener('hashchange',hashChanged);window.addEventListener('keydown',closeNav);onUnmounted(()=>{window.removeEventListener('hashchange',hashChanged);window.removeEventListener('keydown',closeNav);});
const route=computed(()=>{const path=hash.value.replace(/^#\//,'').split('?')[0];return valid.has(path)?path:'support/workbench';});
const group=computed(()=>route.value.split('/')[0]),view=computed(()=>route.value.split('/')[1]);
watch(group,g=>expanded.value=g,{immediate:true});
const title=computed(()=>group.value==='support'?support.find(c=>c.id===view.value)?.title:group.value==='settings'?'平台设置':groups.find(g=>g.id===group.value)?.children.find(c=>c.id===view.value)?.title);
const component=computed(()=>group.value==='support'?(view.value==='todos'?TodosPage:HistoryPage):group.value==='commerce'?CommercePage:group.value==='analysis'?(view.value==='traces'?ReplyRoutesPage:AnalysisPage):group.value==='settings'?SettingsPage:view.value==='models'?ModelsPage:view.value==='recall'?RecallPage:view.value==='prompts'?PromptsPage:KnowledgePage);
const disabled=computed(()=>s.accounts.value.find(a=>a.id===wb.staff.id)?.enabled===false);
const pending=computed(()=>s.tickets.value.filter(t=>t.completion==='PENDING').length);
function enter(path:string){navigate(path);mobileNav.value=false;}
</script>
<template><div class="wb-root pv-app" :class="{'pv-nav-open':mobileNav}"><button v-if="mobileNav" class="pv-nav-scrim" aria-label="关闭导航" @click="mobileNav=false"></button><aside :inert="disabled" class="wb-navigation pv-navigation" aria-label="应用导航"><a class="wb-brand" href="?preview=workbench#/support/workbench"><span class="wb-brand-symbol"><Icon name="ChatLineRound"/></span><strong>智能客服</strong></a><button v-if="mobileNav" class="wb-icon-button pv-nav-close" aria-label="关闭模块导航" @click="mobileNav=false"><Icon name="Close"/></button><button class="wb-shop pv-shop-link" @click="enter('settings/shop')" aria-label="青禾服饰 · 店铺接入"><Icon name="Shop"/><span>青禾服饰</span><span class="pv-tag">淘宝</span></button><button class="wb-ai-service pv-shop-status" aria-label="AI 接待状态，前往 AI 模型配置" @click="enter('knowledge/models')"><i class="wb-dot" :class="{offline:!s.aiEnabled.value}"></i><span>AI 接待{{s.aiEnabled.value?'已开启':'已关闭'}}</span><Icon name="ArrowRight"/></button><div class="pv-nav-scroll"><div class="wb-nav-group-label">客服中心</div><nav class="wb-nav-items"><button v-for="c in support" :key="c.id" :title="c.title" :aria-label="c.title" :aria-current="route===`support/${c.id}`?'page':undefined" :class="{active:route===`support/${c.id}`}" @click="enter(`support/${c.id}`)"><Icon :name="c.icon"/><span>{{c.title}}</span><b v-if="c.id==='todos'&&pending" class="pv-nav-count">{{pending}}</b></button></nav><div class="wb-nav-separator"></div><nav class="wb-nav-items pv-nav-groups"><div v-for="g in groups" :key="g.id" class="pv-nav-group"><button class="pv-group-button" :class="{selected:group===g.id}" :title="g.title" :aria-expanded="expanded===g.id" @click="expanded=expanded===g.id?'':g.id"><Icon :name="g.icon"/><span>{{g.title}}</span><Icon :name="expanded===g.id?'ArrowDown':'ArrowRight'"/></button><div v-if="expanded===g.id" class="pv-nav-children"><button v-for="c in g.children" :key="c.id" :title="c.title" :aria-label="c.title" :data-short="c.id==='models'?'模型':c.id==='chunks'?'切片':c.id==='documents'?'文章':c.title.slice(0,2)" :class="{active:route===`${g.id}/${c.id}`}" :aria-current="route===`${g.id}/${c.id}`?'page':undefined" @click="enter(`${g.id}/${c.id}`)"><span class="pv-nav-child-dot"></span><span>{{c.title}}</span></button></div></div><button :title="'平台设置'" :class="{active:group==='settings'}" @click="enter('settings/shop')"><Icon name="Setting"/><span>平台设置</span></button></nav></div><div class="wb-profile-wrap"><el-dropdown trigger="click" placement="top-start" @command="wb.setOnline($event==='online')"><button class="wb-profile" :disabled="wb.presenceBusy.value" aria-label="调整客服在线状态"><span class="wb-avatar blue"><img v-if="wb.staff.avatar" :src="wb.staff.avatar" alt="客服头像"/><template v-else>{{wb.staff.name.replace('客服','')[0]}}</template></span><span class="wb-profile-info"><strong>{{wb.staff.name}}</strong><small><i class="wb-dot" :class="{offline:!wb.staff.online}"></i>{{wb.staff.online?'在线':'离线'}}</small></span><Icon name="ArrowDown"/></button><template #dropdown><el-dropdown-menu><el-dropdown-item command="online" :disabled="wb.staff.online">切换为在线</el-dropdown-item><el-dropdown-item command="offline" :disabled="!wb.staff.online">切换为离线</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></aside>
<div :inert="disabled" class="wb-workspace pv-workspace"><div class="wb-topbar pv-global-header" :class="{'has-description':!!heading?.description}"><button class="wb-icon-button pv-mobile-menu" aria-label="打开模块导航" @click="mobileNav=true"><Icon name="MoreFilled"/></button><div class="pv-page-identity"><h1>{{heading?.title||title}}</h1><p v-if="heading?.description">{{heading.description}}</p></div></div>
<div v-if="wb.loading.value" class="pv-app-loading"><Icon name="Loading" spin/>正在准备店铺数据…</div><div v-else class="pv-content"><WorkbenchPage v-show="route==='support/workbench'" embedded/><component :is="component" v-if="route!=='support/workbench'" :key="hash" :view="view"/></div></div>
<div v-if="disabled" class="pv-disabled-overlay" role="alertdialog" aria-label="当前账号已停用"><div class="pv-card"><span class="pv-category-symbol"><Icon name="SwitchButton"/></span><h2>当前客服账号已停用</h2><p>不能继续接入或回复，请联系平台处理。</p></div></div>
<ConversationRecordDrawer/><ReplyTraceDialog/></div></template>
