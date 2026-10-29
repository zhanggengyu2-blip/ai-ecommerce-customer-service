<script lang="ts">
import { defineComponent, h, Fragment, type VNode } from 'vue';
import { ElSelect } from 'element-plus/es/components/select/index.mjs';
import { ElOption } from 'element-plus/es/components/select/index.mjs';

// Keep existing option values (including numeric IDs) while using one accessible dropdown.
function options(nodes: VNode[]): VNode[] {
  return nodes.flatMap(node => node.type === Fragment && Array.isArray(node.children)
    ? options(node.children as VNode[]) : node.type === 'option' ? [node] : []);
}
export default defineComponent({
  inheritAttrs: false,
  props: { modelValue: { type: [String, Number], default: '' }, disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(props, { attrs, slots, emit }) {
    return () => h(ElSelect, {
      ...attrs, class: ['pv-select', attrs.class], modelValue: props.modelValue,
      disabled: props.disabled, placeholder: '请选择', fitInputWidth: true, emptyValues: [null, undefined],
      'onUpdate:modelValue': (value: string | number) => emit('update:modelValue', value),
      onChange: (value: string | number) => emit('change', value),
    }, { default: () => options(slots.default?.() || []).map(node => {
      const label = String(node.children ?? '');
      return h(ElOption, { label, value: node.props?.value ?? label,
        disabled: node.props?.disabled !== undefined && node.props.disabled !== false });
    }) });
  },
});
</script>
