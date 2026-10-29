export function adminMenus(role: string) {
  const admin = ["SUPER_ADMIN", "ADMIN"].includes(role),
    read = ["SUPER_ADMIN", "ADMIN", "KNOWLEDGE_MANAGER", "VIEWER"].includes(
      role,
    );
  return [
    {
      title: "总览",
      icon: "HomeFilled",
      visible: read,
      items: [{ key: "dashboard", label: "Dashboard", icon: "Odometer" }],
    },
    {
      title: "客服中心",
      icon: "Service",
      visible: true,
      items: [
        { key: "support-live", label: "实时会话", icon: "ChatDotRound" },
        { key: "support-pending", label: "待处理", icon: "Clock" },
        { key: "support-history", label: "历史会话", icon: "ChatLineRound" },
        { key: "support-handoff", label: "转人工队列", icon: "Switch" },
      ],
    },
    {
      title: "电商管理",
      icon: "ShoppingCart",
      visible: admin || role === "VIEWER",
      items: [
        { key: "eshop-customers", label: "客户管理", icon: "User" },
        { key: "eshop-products", label: "商品管理", icon: "Goods" },
        { key: "eshop-orders", label: "订单管理", icon: "Tickets" },
        { key: "eshop-payments", label: "支付记录", icon: "Money" },
        { key: "eshop-shipments", label: "物流管理", icon: "Van" },
        { key: "eshop-refunds", label: "退款售后", icon: "Refresh" },
        { key: "eshop-inventory", label: "库存流水", icon: "Coin" },
      ],
    },
    {
      title: "知识库",
      icon: "Reading",
      visible: read,
      items: [
        { key: "knowledge", label: "知识库概览", icon: "Collection" },
        { key: "documents", label: "文档管理", icon: "Document" },
      ],
    },
    {
      title: "AI 与检索",
      icon: "Cpu",
      visible: read,
      items: [
        { key: "config-model", label: "LLM", icon: "Cpu" },
        { key: "config-prompt", label: "Prompt", icon: "EditPen" },
        { key: "embedding", label: "模型与向量", icon: "Connection" },
        { key: "config-rag", label: "检索参数", icon: "Search" },
      ],
    },
    {
      title: "分析与反馈",
      icon: "DataAnalysis",
      visible: read,
      items: [
        { key: "metrics", label: "运营指标", icon: "TrendCharts" },
        { key: "feedback", label: "用户反馈", icon: "ChatSquare" },
        { key: "unresolved", label: "未解决问题", icon: "Warning" },
        { key: "popular", label: "热门问题", icon: "TrendCharts" },
        { key: "executions", label: "回复路由记录", icon: "Connection" },
      ],
    },
    {
      title: "系统",
      icon: "Setting",
      visible: read,
      items: [
        ...(admin ? [{ key: "accounts", label: "接入账号", icon: "Connection" }] : []),
        ...(admin ? [{ key: "users", label: "用户管理", icon: "User" }] : []),
        { key: "roles", label: "角色与权限", icon: "Key" },
        { key: "api", label: "API 与服务", icon: "Link" },
        { key: "audit", label: "Audit Log", icon: "Document" },
      ],
    },
  ].filter((group) => group.visible);
}
