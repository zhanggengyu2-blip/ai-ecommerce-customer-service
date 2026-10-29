<script setup lang="ts">
import { reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import { usePreview, type Product } from '../usePreviewStore';
import Icon from '../../workbench/components/WorkbenchIcon.vue';
const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [open: boolean]; saved: [] }>();
const s = usePreview();
let nextRow = 1, imageRequest = 0;
const sku = () => ({ key: nextRow++, name: '', price: 129, stock: 0 });
const form = reactive({ name: '', imageUrl: '', active: true, variants: [sku()] });
const error = ref(''), imageError = ref(''), reading = ref(false), upload = ref<HTMLInputElement | null>(null);
watch(() => [form.name, form.variants.map(v => `${v.name}:${v.price}:${v.stock}`).join('|')], () => { error.value = ''; });
watch(() => props.modelValue, open => {
  imageRequest++; reading.value = false;
  if (open) {
    Object.assign(form, { name: '', imageUrl: '', active: true, variants: [sku()] });
    error.value = ''; imageError.value = '';
  }
});
async function readImage(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0];
  input.value = '';
  if (!file) return;
  const request = ++imageRequest;
  imageError.value = ''; reading.value = false;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
    imageError.value = '请选择不超过 5 MB 的 JPG、PNG 或 WebP 图片。'; return;
  }
  reading.value = true;
  try {
    const url = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file);
    });
    const image = new Image(); image.src = url; await image.decode();
    if (request === imageRequest) form.imageUrl = url;
  } catch {
    if (request === imageRequest) imageError.value = '无法读取这张图片，请重新选择。';
  } finally { if (request === imageRequest) reading.value = false; }
}
function save() {
  error.value = '';
  if (reading.value) return;
  if (!form.name.trim()) { error.value = '请填写商品名称。'; return; }
  const names = new Set<string>();
  for (const [index, variant] of form.variants.entries()) {
    if (!variant.name.trim()) { error.value = `请填写规格 ${index + 1} 的名称。`; return; }
    if (names.has(variant.name.trim())) { error.value = '规格名称不能重复。'; return; }
    names.add(variant.name.trim());
    if (!Number.isFinite(variant.price) || variant.price < 0.01 || !Number.isSafeInteger(Math.round(variant.price * 100))) {
      error.value = `请为规格 ${index + 1} 填写大于零的价格。`; return;
    }
    if (!Number.isSafeInteger(variant.stock) || variant.stock < 0) {
      error.value = `请为规格 ${index + 1} 填写非负整数库存。`; return;
    }
  }
  const groupId = s.products.value.reduce((id, p) => Math.max(id, p.id + 1), Date.now());
  const variants: Product[] = form.variants.map((v, index) => ({
    id: groupId + index, groupId, name: form.name.trim(), imageUrl: form.imageUrl,
    variant: v.name.trim(), price: Math.round(v.price * 100) / 100,
    stock: 0, reserved: 0, active: form.active, thumbnail: 'shirt',
  }));
  // Validate every row before adding the product or any inventory entries.
  s.products.value.unshift(...variants);
  variants.forEach((variant, index) => {
    if (form.variants[index].stock) s.stock(variant, form.variants[index].stock, '商品初始入库');
  });
  emit('update:modelValue', false); emit('saved'); ElMessage.success('商品已新增');
}
</script>
<template>
  <el-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)"
    title="新增商品" width="740px" class="wb-dialog pv-new-product-dialog" append-to-body align-center>
    <form id="pv-new-product-form" class="pv-form" @submit.prevent="save">
      <div class="pv-new-product-main">
        <div class="pv-product-image-field">
          <span>商品图片 <small>选填</small></span>
          <button type="button" class="pv-product-image-upload" :disabled="reading" @click="upload?.click()" :aria-label="form.imageUrl ? '更换商品图片' : '上传商品图片'">
            <img v-if="form.imageUrl" :src="form.imageUrl" alt="商品图片预览"/>
            <template v-else><Icon :name="reading ? 'Loading' : 'Plus'" :spin="reading"/><span>{{reading ? '正在读取' : '上传图片'}}</span></template>
          </button>
          <input ref="upload" hidden type="file" accept="image/jpeg,image/png,image/webp" @change="readImage"/>
          <button v-if="form.imageUrl" type="button" class="wb-text-button" @click="imageRequest++; reading=false; form.imageUrl=''">移除图片</button>
        </div>
        <label>商品名称<input v-model="form.name" maxlength="100" placeholder="如：休闲直筒长裤" aria-label="商品名称" required/><small>图片支持 JPG、PNG、WebP，大小不超过 5 MB。</small><span v-if="imageError" class="wb-form-error" role="alert">{{imageError}}</span></label>
      </div>
      <div class="pv-product-variants-heading"><div><h3>商品规格</h3><p>每个规格分别设置售价和初始库存。</p></div><button type="button" class="wb-btn" @click="form.variants.push(sku())"><Icon name="Plus"/>添加规格</button></div>
      <div class="pv-product-variants">
        <div v-for="(variant, index) in form.variants" :key="variant.key" class="pv-sku-row">
          <label>规格 {{index + 1}}<input v-model="variant.name" maxlength="100" placeholder="如：黑色 / M 码" :aria-label="`规格 ${index + 1} 名称`" required/></label>
          <label>售价（元）<input v-model.number="variant.price" type="number" min="0.01" step="0.01" :aria-label="`规格 ${index + 1} 售价`" required/></label>
          <label>初始库存<input v-model.number="variant.stock" type="number" min="0" step="1" :aria-label="`规格 ${index + 1} 库存`" required/></label>
          <button type="button" class="wb-icon-button pv-remove-sku" :disabled="form.variants.length === 1" @click="form.variants.splice(index,1)" :aria-label="`删除规格 ${index + 1}`" :title="form.variants.length === 1 ? '至少保留一个规格' : '删除规格'"><Icon name="Close"/></button>
        </div>
      </div>
      <label class="pv-check"><input v-model="form.active" type="checkbox"/>上架销售</label>
      <p v-if="error" class="wb-form-error" role="alert">{{error}}</p>
    </form>
    <template #footer><button class="wb-btn" @click="emit('update:modelValue', false)">取消</button><button class="wb-btn primary" type="submit" form="pv-new-product-form" :disabled="reading">确认保存</button></template>
  </el-dialog>
</template>
