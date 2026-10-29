import { computed, onMounted, reactive, ref, watch } from "vue";
import { useLocalList } from "../../composables/useLocalList";
import { ElMessage } from "element-plus/es/components/message/index.mjs";
import { ElMessageBox } from "element-plus/es/components/message-box/index.mjs";
import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";
import { api } from "../../api";

type User = {
  id: number;
  user_id: number;
  username: string;
  name: string;
  phone: string;
  address: string;
};
type Product = {
  id: number;
  sku: string;
  name: string;
  price: string;
  inventory: number;
  reserved: number;
  status: string;
  description: string;
};
type Order = {
  id: number;
  user_id: number;
  order_id: string;
  customer_username: string;
  product_sku: string;
  quantity: number;
  amount: string;
  status: string;
  shipping_status: string;
  refund_status: string;
  receiver: { name: string; phone: string; address: string };
  items: { name: string; sku: string; quantity: number; unit_price: string }[];
  created_at: string;
};
type Payment = {
  id: number;
  order_id: string;
  customer: string;
  payment_no: string;
  method: string;
  amount: string;
  refunded_amount: string;
  status: string;
};
type Shipment = {
  id: number;
  order_id: string;
  customer: string;
  carrier: string;
  tracking_number: string;
  status: string;
  events: { time: string; status: string; description: string }[];
};
type Refund = {
  id: number;
  order_id: string;
  customer: string;
  refund_no: string;
  amount: string;
  reason: string;
  status: string;
  original_status: string;
  return_tracking: string;
};
type StockLog = {
  id: number;
  sku: string;
  delta: number;
  reserved_delta: number;
  available_after: number;
  reserved_after: number;
  reason: string;
  actor: string;
  created_at: string;
};
export function useEshop(
  props: { view: string; token: string; readonly: boolean; accountId: number },
  emit: (event: "error" | "customerSession", ...args: any[]) => void,
) {
  const customers = ref<User[]>([]),
    products = ref<Product[]>([]),
    orders = ref<Order[]>([]);
  const payments = ref<Payment[]>([]),
    shipments = ref<Shipment[]>([]),
    refunds = ref<Refund[]>([]),
    logs = ref<StockLog[]>([]);
  const busy = ref(false),
    loading = ref(false);
  const dialog = ref(""),
    selected = ref<Order | null>(null),
    editing = ref<Product | null>(null);
  const dialogVisible = computed({
    get: () => !!dialog.value,
    set: (value) => {
      if (!value) dialog.value = "";
    },
  });
  const customerMode = ref("new"),
    editingCustomer = ref<User | null>(null);
  const availableUsers = ref<
    { id: number; username: string; display_name: string; kind: string }[]
  >([]);
  const customerForm = reactive({
    user_id: undefined as number | undefined,
    username: "",
    name: "",
    phone: "",
    address: "",
  });
  const productForm = reactive({
    sku: "",
    name: "",
    price: 99,
    inventory: 10,
    status: "ON_SALE",
    description: "",
  });
  const orderForm = reactive({
    user_id: undefined as number | undefined,
    product_id: undefined as number | undefined,
    quantity: 1,
  });
  const stockForm = reactive({ delta: 10, reason: "运营补货" });
  const shipForm = reactive({ carrier: "顺丰（模拟）", tracking_number: "" });
  const payMethod = ref("MOCK_ALIPAY");
  const titles: Record<string, string> = {
    customers: "客户管理",
    products: "商品管理",
    orders: "订单管理",
    payments: "支付记录",
    shipments: "物流管理",
    refunds: "退款售后",
    inventory: "库存流水",
  };
  const statusLabels: Record<string, string> = {
    UNPAID: "待支付",
    PAID: "已支付 / 待发货",
    SHIPPED: "已发货",
    DELIVERED: "已签收",
    REFUNDING: "退款处理中",
    REFUNDED: "已退款",
    CANCELLED: "已取消",
    PENDING: "待发货",
    IN_TRANSIT: "运输中",
    OUT_FOR_DELIVERY: "派送中",
    NONE: "无售后",
    REQUESTED: "待审核",
    APPROVED: "已批准",
    RECEIVED: "退货已验收",
    COMPLETED: "退款完成",
    REJECTED: "已驳回",
    SUCCESS: "支付成功",
    ON_SALE: "已上架",
    OFF_SALE: "已下架",
  };
  const paymentLabels: Record<string, string> = {
    MOCK_ALIPAY: "模拟支付宝",
    MOCK_WECHAT: "模拟微信",
    MOCK_BANK: "模拟银行卡",
  };
  const refundActions: Record<string, string> = {
    approve: "批准退款",
    reject: "驳回申请",
    complete: "模拟原路退款到账",
  };
  function label(value: string) {
    return statusLabels[value] || value;
  }
  function tag(value: string) {
    return ["CANCELLED", "OFF_SALE", "REJECTED"].includes(value)
      ? "info"
      : ["REFUNDING", "REQUESTED", "UNPAID"].includes(value)
        ? "warning"
        : "success";
  }
  const activeRows = computed(
    () =>
      (({
        customers: customers.value,
        products: products.value,
        orders: orders.value,
        payments: payments.value,
        shipments: shipments.value,
        refunds: refunds.value,
        inventory: logs.value,
      })[props.view] || []) as any[],
  );
  const list = useLocalList(activeRows);
  const orderProduct = computed(() =>
    products.value.find((p) => p.id === orderForm.product_id),
  );
  const orderCustomer = computed(() =>
    customers.value.find((c) => c.user_id === orderForm.user_id),
  );
  const amountPreview = computed(() =>
    ((Number(orderProduct.value?.price) || 0) * orderForm.quantity).toFixed(2),
  );
  const prefix = "/api/admin/eshop";
  const scope = (path: string) => `${prefix}${path}${path.includes('?') ? '&' : '?'}account_id=${props.accountId}`;
  async function load() {
    loading.value = true;
    try {
      const tasks: Record<string, () => Promise<void>> = {
        customers: async () => {
          customers.value = await api<User[]>(
            scope('/customers'),
            "GET",
            undefined,
            props.token,
          );
        },
        products: async () => {
          products.value = await api<Product[]>(
            scope('/products'),
            "GET",
            undefined,
            props.token,
          );
        },
        orders: async () => {
          orders.value = await api<Order[]>(
            scope('/orders'),
            "GET",
            undefined,
            props.token,
          );
        },
        payments: async () => {
          payments.value = await api<Payment[]>(
            scope('/payments'),
            "GET",
            undefined,
            props.token,
          );
        },
        shipments: async () => {
          shipments.value = await api<Shipment[]>(
            scope('/shipments'),
            "GET",
            undefined,
            props.token,
          );
        },
        refunds: async () => {
          refunds.value = await api<Refund[]>(
            scope('/refunds'),
            "GET",
            undefined,
            props.token,
          );
        },
        inventory: async () => {
          logs.value = await api<StockLog[]>(
            scope('/inventory-logs'),
            "GET",
            undefined,
            props.token,
          );
        },
        users: async () => {
          availableUsers.value = await api<typeof availableUsers.value>(
            scope('/customer-users'),
            "GET",
            undefined,
            props.token,
          );
        },
      };
      const dependencies: Record<string, string[]> = {
        customers: ["customers", "users"],
        orders: ["orders", "customers", "products"],
        shipments: ["shipments", "orders"],
      };
      await Promise.all(
        (dependencies[props.view] || [props.view]).map((key) => tasks[key]!()),
      );
    } catch (error) {
      emit("error", error);
    } finally {
      loading.value = false;
    }
  }
  async function write(
    path: string,
    body?: unknown,
    method = "POST",
    message = "操作成功",
  ) {
    if (busy.value) return false;
    busy.value = true;
    try {
      await api(scope(path), method, body, props.token);
      ElMessage.success(message);
      dialog.value = "";
      await load();
      return true;
    } catch (error) {
      emit("error", error);
      return false;
    } finally {
      busy.value = false;
    }
  }
  function openCustomer(customer?: User) {
    editingCustomer.value = customer || null;
    customerMode.value = "new";
    Object.assign(
      customerForm,
      customer || {
        user_id: undefined,
        username: "",
        name: "",
        phone: "",
        address: "",
      },
    );
    dialog.value = "customer";
  }
  async function saveCustomer() {
    const { name, phone, address } = customerForm;
    if (!name.trim() || !phone.trim() || !address.trim()) {
      ElMessage.warning("请填写姓名、电话和收货地址");
      return;
    }
    if (editingCustomer.value)
      await write(
        `/customers/${editingCustomer.value.user_id}`,
        { name, phone, address },
        "PATCH",
      );
    else {
      if (
        (customerMode.value === "new" && !customerForm.username.trim()) ||
        (customerMode.value === "existing" && !customerForm.user_id)
      ) {
        ElMessage.warning("请填写用户名或选择已有用户");
        return;
      }
      await write("/customers", {
        name,
        phone,
        address,
        ...(customerMode.value === "existing"
          ? { user_id: customerForm.user_id }
          : { username: customerForm.username.trim() }),
      });
    }
  }
  function openProduct(product?: Product) {
    editing.value = product || null;
    Object.assign(
      productForm,
      product
        ? { ...product, price: Number(product.price) }
        : {
            sku: "",
            name: "",
            price: 99,
            inventory: 10,
            status: "ON_SALE",
            description: "",
          },
    );
    dialog.value = "product";
  }
  async function saveProduct() {
    if (editing.value) {
      const { name, price, status, description } = productForm;
      await write(
        `/products/${editing.value.id}`,
        { name, price, status, description },
        "PATCH",
      );
    } else await write("/products", productForm);
  }
  async function createOrder() {
    if (!orderForm.user_id || !orderForm.product_id) {
      ElMessage.warning("请选择客户和商品");
      return;
    }
    await write(
      "/orders",
      orderForm,
      "POST",
      "订单已生成，可售库存已占用。请继续模拟支付",
    );
  }
  function openOrderAction(order: Order, action: string) {
    selected.value = order;
    shipForm.tracking_number = `MOCK-${Date.now()}`;
    dialog.value = action;
  }
  async function confirmOperation(
    title: string,
    action: () => Promise<unknown>,
  ) {
    try {
      await ElMessageBox.confirm(title, "确认模拟操作", {
        confirmButtonText: "确认",
        cancelButtonText: "取消",
        type: "warning",
      });
      await action();
    } catch (error) {
      if (error !== "cancel" && error !== "close") emit("error", error);
    }
  }
  async function cancelOrder(order: Order) {
    await confirmOperation(
      `取消订单 ${order.order_id}？${order.status === "PAID" ? "已支付金额将模拟原路退回。" : "占用库存将释放。"}`,
      () => write(`/orders/${order.id}/cancel`),
    );
  }
  async function toggleProduct(product: Product) {
    const status = product.status === "ON_SALE" ? "OFF_SALE" : "ON_SALE";
    await confirmOperation(
      `将 ${product.name} ${status === "ON_SALE" ? "上架" : "下架"}？已生成订单保持不变。`,
      () => write(`/products/${product.id}`, { status }, "PATCH"),
    );
  }
  async function updateLogistics(shipment: Shipment, status: string) {
    const order = orders.value.find((o) => o.order_id === shipment.order_id);
    if (!order) return;
    await confirmOperation(
      `将订单 ${order.order_id} 的物流更新为“${label(status)}”？`,
      () =>
        write(`/orders/${order.id}/logistics`, {
          status,
          description:
            status === "DELIVERED"
              ? "客户已签收（模拟）"
              : "快递员正在派送（模拟）",
        }),
    );
  }
  async function refund(order: Order) {
    try {
      const { value } = await ElMessageBox.prompt(
        "填写本次全额退款原因",
        `订单 ${order.order_id}`,
        {
          confirmButtonText: "提交申请",
          cancelButtonText: "取消",
          inputValue: "客户申请退货退款",
          inputValidator: (value) => !!value?.trim() || "请填写原因",
        },
      );
      await write(`/orders/${order.id}/refund`, { reason: value });
    } catch (error) {
      if (error !== "cancel" && error !== "close") emit("error", error);
    }
  }
  async function processRefund(row: Refund, action: string) {
    if (action === "receive") {
      try {
        const { value } = await ElMessageBox.prompt(
          "确认已收到并验收退货，填写客户退货运单号；验收后商品将回库。",
          "退货验收",
          {
            confirmButtonText: "确认验收",
            cancelButtonText: "取消",
            inputValidator: (value) => !!value?.trim() || "请填写退货运单号",
          },
        );
        await write(`/refunds/${row.id}/process`, {
          action,
          return_tracking: value,
        });
      } catch (error) {
        if (error !== "cancel" && error !== "close") emit("error", error);
      }
    } else
      await confirmOperation(
        `${refundActions[action]}：${row.refund_no}，金额 ¥${row.amount}？`,
        () => write(`/refunds/${row.id}/process`, { action }),
      );
  }
  async function enterCustomer(customer: User) {
    if (busy.value) return;
    busy.value = true;
    try {
      const result = await api<{ access_token: string; display_name: string }>(
        scope(`/customers/${customer.user_id}/session`),
        "POST",
        {},
        props.token,
      );
      emit("customerSession", result.access_token, result.display_name, props.accountId);
    } catch (error) {
      emit("error", error);
    } finally {
      busy.value = false;
    }
  }
  onMounted(load);
  watch(
    () => props.view,
    () => {
      list.reset();
      dialog.value = "";
      load();
    },
  );
  watch(() => props.accountId, () => { list.reset(); load(); });

  return {
    openCustomer,
    saveCustomer,
    editingCustomer,
    customers,
    products,
    orders,
    payments,
    shipments,
    refunds,
    logs,
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
    titles,
    statusLabels,
    paymentLabels,
    refundActions,
    label,
    tag,
    list,
    orderProduct,
    orderCustomer,
    amountPreview,
    load,
    write,
    openProduct,
    saveProduct,
    createOrder,
    openOrderAction,
    confirmOperation,
    toggleProduct,
    cancelOrder,
    updateLogistics,
    refund,
    processRefund,
    enterCustomer,
  };
}
export type EshopContext = ReturnType<typeof useEshop>;
