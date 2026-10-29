<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import { usePreview } from '../../features/preview/usePreviewStore';
import PageHeading from '../../features/preview/components/PageHeading.vue';
import Icon from '../../features/workbench/components/WorkbenchIcon.vue';
const editing=ref(false);
const s=usePreview(),id=ref(1),text=ref(s.prompts.value[0].content),current=computed(()=>s.prompts.value.find(p=>p.id===id.value)!);
watch(id,()=>{text.value=current.value.content;editing.value=false;});
function save(){if(!text.value.trim()){ElMessage.warning('模板内容不能为空');return;}current.value.content=text.value.trim();editing.value=false;ElMessage.success('Prompt 模板已更新');}
</script>
<template><div class="pv-page"><PageHeading title="Prompt 模板" description="调整 AI 在不同客服场景下的目标、语气与回复要求。" eyebrow="AI 与知识"/><div class="pv-prompt-grid"><section class="pv-card pv-prompt-list"><button v-for="p in s.prompts.value" :key="p.id" :class="{active:id===p.id}" @click="id=p.id"><span class="pv-template-icon"><Icon name="Document"/></span><div><strong>{{p.name}}</strong><small>{{p.scene}}</small></div><Icon name="ArrowRight"/></button><div class="pv-prompt-baseline"><Icon name="InfoFilled"/><p>基础身份与安全边界由系统统一维护。这里编辑的是业务模板。</p></div></section><section class="pv-card pv-prompt-editor"><div class="pv-panel-heading"><div><strong>{{current.name}}</strong><small>{{current.scene}}</small></div><div class="pv-card-actions"><span class="pv-tag blue">预置模板 · 可编辑</span><template v-if="editing"><button class="wb-btn" @click="text=current.content;editing=false">取消</button><button class="wb-btn primary" @click="save">保存模板</button></template><button v-else class="wb-btn primary" @click="editing=true">编辑</button></div></div><textarea v-model="text" :readonly="!editing" :class="{'is-readonly':!editing}" spellcheck="false" aria-label="Prompt 模板内容"/><div class="pv-editor-bottom"><span>{{text.length}} 字</span><span>{{editing?'保存后生效，取消则保留原内容':'点击编辑可修改模板内容'}}</span></div></section></div></div></template>
