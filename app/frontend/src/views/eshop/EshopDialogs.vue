<script setup lang="ts">
import { inject } from "vue";
import type { EshopContext } from "./useEshop";
const {
  editingCustomer,
  saveCustomer,
  customers,
  products,
  orders,
  busy,
  loading,
  dialog,
  selected,
  editing,
  dialogVisible,
  customerMode,
  availableUsers,
  customerForm,
  productForm,
  orderForm,
  stockForm,
  shipForm,
  payMethod,
  label,
  orderProduct,
  orderCustomer,
  amountPreview,
  write,
  saveProduct,
  createOrder,
} = inject<EshopContext>("eshop")!;
</script>
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="
      (
        {
          customer: editingCustomer ? '编辑客户' : '新增客户',
          product: editing ? '编辑商品' : '新增商品',
          order: '创建订单',
          stock: '调整可售库存',
          pay: '模拟支付',
          ship: '模拟发货',
          detail: '订单详情',
        } as Record<string, string>
      )[dialog]
    "
    width="560px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-form label-position="top" @submit.prevent>
      <template v-if="dialog === 'customer'">
        <el-form-item v-if="!editingCustomer" label="用户关联">
          <el-radio-group v-model="customerMode">
            <el-radio-button value="new">新建客户端用户</el-radio-button>
            <el-radio-button value="existing"
              >关联已有客户端用户</el-radio-button
            ></el-radio-group
          ></el-form-item
        >
        <el-form-item
          v-if="!editingCustomer && customerMode === 'new'"
          label="登录用户名（例如 zhangsan）"
        >
          <el-input v-model="customerForm.username" />
        </el-form-item>
        <el-form-item v-else-if="!editingCustomer" label="已有客户端用户">
          <el-select v-model="customerForm.user_id" filterable>
            <el-option
              v-for="u in availableUsers"
              :key="u.id"
              :value="u.id"
              :label="`${u.display_name} / ${u.username} / #${u.id}`"
            /> </el-select
        ></el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="customerForm.name" />
        </el-form-item>
        <el-form-item label="电话">
          <el-input v-model="customerForm.phone" />
        </el-form-item>
        <el-form-item label="收货地址">
          <el-input v-model="customerForm.address" /> </el-form-item
      ></template>
      <template v-if="dialog === 'product'">
        <el-form-item label="SKU">
          <el-input v-model="productForm.sku" :disabled="!!editing" />
        </el-form-item>
        <el-form-item label="商品名称">
          <el-input v-model="productForm.name" />
        </el-form-item>
        <el-form-item label="价格（元）">
          <el-input-number
            v-model="productForm.price"
            :min="0.01"
            :precision="2"
            :max="99999999"
          />
        </el-form-item>
        <el-form-item v-if="!editing" label="初始库存">
          <el-input-number
            v-model="productForm.inventory"
            :min="0"
            :max="1000000"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="productForm.status">
            <el-radio value="ON_SALE">上架</el-radio>
            <el-radio value="OFF_SALE">下架</el-radio></el-radio-group
          ></el-form-item
        >
        <el-form-item label="描述">
          <el-input
            v-model="productForm.description"
            type="textarea"
          /> </el-form-item
      ></template>
      <template v-if="dialog === 'order'">
        <el-form-item label="客户">
          <el-select
            v-model="orderForm.user_id"
            filterable
            placeholder="请选择客户"
          >
            <el-option
              v-for="c in customers"
              :key="c.id"
              :value="c.user_id"
              :label="`${c.name}（${c.username} / 用户 #${c.user_id}）`"
            /> </el-select
        ></el-form-item>
        <el-form-item label="商品">
          <el-select
            v-model="orderForm.product_id"
            filterable
            placeholder="请选择已上架商品"
          >
            <el-option
              v-for="p in products"
              :key="p.id"
              :value="p.id"
              :disabled="p.status !== 'ON_SALE' || p.inventory < 1"
              :label="`${p.name} / ${p.sku} / ¥${p.price} / 可售 ${p.inventory}`"
            /> </el-select
        ></el-form-item>
        <el-form-item label="数量">
          <el-input-number
            v-model="orderForm.quantity"
            :min="1"
            :max="Math.min(orderProduct?.inventory || 1, 1000)"
          />
        </el-form-item>
        <p>
          订单金额：<strong>¥{{ amountPreview }}</strong>
        </p>
        <p>
          收货信息：{{ orderCustomer?.name }} {{ orderCustomer?.phone }}
          {{ orderCustomer?.address }}
        </p>
        <el-alert
          title="创建订单将立即占用可售库存；支付与发货需分别操作。"
          :closable="false"
      /></template>
      <template v-if="dialog === 'stock'"
        ><p>
          {{ editing?.name }} · 当前可售 {{ editing?.inventory }}，占用
          {{ editing?.reserved }}
        </p>
        <el-form-item label="增减数量（正数补货，负数减少可售库存）">
          <el-input-number
            v-model="stockForm.delta"
            :min="-(editing?.inventory || 0)"
            :max="1000000"
          />
        </el-form-item>
        <el-form-item label="调整原因">
          <el-input v-model="stockForm.reason" /> </el-form-item
      ></template>
      <template v-if="dialog === 'pay'"
        ><p>订单 {{ selected?.order_id }} · 金额 ¥{{ selected?.amount }}</p>
        <el-form-item label="模拟支付方式">
          <el-select v-model="payMethod">
            <el-option value="MOCK_ALIPAY" label="模拟支付宝" />
            <el-option value="MOCK_WECHAT" label="模拟微信" />
            <el-option value="MOCK_BANK" label="模拟银行卡" /> </el-select
        ></el-form-item>
        <el-alert
          title="此操作仅生成本地支付记录，不扣取真实资金。"
          :closable="false"
      /></template>
      <template v-if="dialog === 'ship'"
        ><p>订单 {{ selected?.order_id }}</p>
        <p>
          {{ selected?.receiver.name }} {{ selected?.receiver.phone }}
          {{ selected?.receiver.address }}
        </p>
        <el-form-item label="承运商">
          <el-input v-model="shipForm.carrier" />
        </el-form-item>
        <el-form-item label="模拟运单号">
          <el-input v-model="shipForm.tracking_number" /> </el-form-item
      ></template>
      <template v-if="dialog === 'detail'">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="订单">{{
            selected?.order_id
          }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{
            selected?.customer_username
          }}</el-descriptions-item>
          <el-descriptions-item label="金额"
            >¥{{ selected?.amount }}</el-descriptions-item
          >
          <el-descriptions-item label="订单状态">{{
            label(selected?.status || "")
          }}</el-descriptions-item>
          <el-descriptions-item label="售后状态">{{
            label(selected?.refund_status || "")
          }}</el-descriptions-item>
          <el-descriptions-item label="收件信息"
            >{{ selected?.receiver.name }} {{ selected?.receiver.phone }}
            {{ selected?.receiver.address }}</el-descriptions-item
          ></el-descriptions
        >
        <el-table :data="selected?.items || []">
          <el-table-column prop="name" label="商品快照" />
          <el-table-column prop="unit_price" label="单价" />
          <el-table-column prop="quantity" label="数量" /> </el-table
      ></template>
    </el-form>
    <template #footer>
      <el-button @click="dialog = ''">关闭</el-button>
      <el-button
        v-if="dialog !== 'detail'"
        type="primary"
        :loading="busy"
        @click="
          dialog === 'customer'
            ? saveCustomer()
            : dialog === 'product'
              ? saveProduct()
              : dialog === 'order'
                ? createOrder()
                : dialog === 'stock'
                  ? write(`/products/${editing?.id}/inventory`, stockForm)
                  : dialog === 'pay'
                    ? write(`/orders/${selected?.id}/pay`, {
                        method: payMethod,
                      })
                    : write(`/orders/${selected?.id}/ship`, shipForm)
        "
        >确认{{
          dialog === "pay"
            ? "模拟支付"
            : dialog === "ship"
              ? "模拟发货"
              : "保存"
        }}</el-button
      ></template
    >
  </el-dialog>
</template>
