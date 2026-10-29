export const roleRows = [
  {
    role: "CUSTOMER",
    name: "客户",
    permissions: "本人的会话、订单、物流和售后",
  },
  { role: "GUEST", name: "游客", permissions: "本人的会话和订单查询" },
  { role: "SUPER_ADMIN", name: "超级管理员", permissions: "全部功能" },
  {
    role: "ADMIN",
    name: "管理员",
    permissions: "客服、知识、AI 配置、电商管理、用户管理和审计",
  },
  {
    role: "CUSTOMER_SERVICE",
    name: "人工客服",
    permissions: "查看会话、接管、回复与结束本人接管的会话",
  },
  {
    role: "KNOWLEDGE_MANAGER",
    name: "知识运营",
    permissions: "知识维护、会话只读、配置只读、指标与审计",
  },
  {
    role: "VIEWER",
    name: "只读用户",
    permissions: "知识、会话、电商管理、配置、指标及审计只读",
  },
];
export const staffRoles = roleRows.filter(
  (row) => !["CUSTOMER", "GUEST", "SUPER_ADMIN"].includes(row.role),
);
export type AdminProps = {
  token: string;
  role: string;
  page: string;
  currentUserId: number;
  accountId?: number | null;
};
export type UnifiedUser = {
  id: number;
  kind: string;
  user_type: string;
  username: string;
  role: string;
  display_name: string;
  email?: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
};
