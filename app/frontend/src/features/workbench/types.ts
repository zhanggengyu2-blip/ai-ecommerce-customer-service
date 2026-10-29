export type ConversationStatus = 'AI_ACTIVE' | 'WAITING_USER' | 'HUMAN_ACTIVE' | 'CLOSED';
export type MessageKind = 'text' | 'order' | 'image' | 'divider';
export type TicketType = 'RETURN_REFUND' | 'REFUND_ONLY' | 'EXCHANGE' | 'CHANGE_ADDRESS' | 'RESEND' | 'CANCEL_ORDER' | 'OTHER';

export interface WorkbenchMessage {
  id: number;
  sender: 'customer' | 'ai' | 'agent' | 'system';
  name: string;
  kind: MessageKind;
  content: string;
  createdAt: string;
  orderId?: number;
  imageUrl?: string;
  citations?: {document_title: string; version: number; content: string}[];
  traceId?: string;
}

export interface WorkbenchOrder {
  id: number;
  number: string;
  product: string;
  variant: string;
  quantity: number;
  amount: number;
  thumbnail: 'trousers' | 'knit' | 'shirt';
  imageUrl?: string;
  status: string;
  paidAt: string;
  receiver: string;
  address: string;
  carrier: string;
  tracking: string;
}

export interface WorkbenchTicket {
  id: number;
  number: string;
  conversationId: number;
  customerId: number;
  orderId: number;
  types: TicketType[];
  description: string;
  refundAmount: string;
  exchangeTarget: string;
  newAddress: string;
  completion: 'PENDING' | 'DONE';
  source: 'AI' | 'MANUAL';
  createdAt: string;
  revision: number;
  completedAt?: string;
  completedBy?: string;
}

export interface TicketInput {
  conversationId: number;
  orderId: number;
  types: TicketType[];
  description: string;
  refundAmount: string;
  exchangeTarget: string;
  newAddress: string;
}

export interface WorkbenchConversation {
  id: number;
  customerId: number;
  customer: string;
  avatar: string;
  tone: 'blue' | 'rose' | 'teal' | 'amber' | 'slate';
  status: ConversationStatus;
  agentId: number | null;
  agent: string | null;
  lastMessageAt: string;
  waitingSince?: string;
  unread: boolean;
  messages: WorkbenchMessage[];
  orders: WorkbenchOrder[];
  tickets: WorkbenchTicket[];
  suggestion: string;
  summary?: string;
  timelineHistory?: WorkbenchMessage[];
  history: HistoryConversation[];
}

export interface HistoryConversation {
  id: number;
  endedAt: string;
  agent: string;
  summary: string;
  messages: WorkbenchMessage[];
}

export interface WorkbenchSnapshot {
  staff: { id: number; name: string; online: boolean };
  conversations: WorkbenchConversation[];
}

export const ticketTypeLabels: Record<TicketType, string> = {
  RETURN_REFUND: '退货退款', REFUND_ONLY: '仅退款', EXCHANGE: '换货',
  CHANGE_ADDRESS: '修改收货地址', RESEND: '补发', CANCEL_ORDER: '取消订单', OTHER: '其他售后',
};

export const statusLabels: Record<ConversationStatus, string> = {
  AI_ACTIVE: 'AI 接待', WAITING_USER: '等待接入', HUMAN_ACTIVE: '人工接待', CLOSED: '已完结',
};

export const money = (amount: number) => new Intl.NumberFormat('zh-CN', {
  style: 'currency', currency: 'CNY', minimumFractionDigits: 2,
}).format(amount);

export const timeOf = (value: string) => new Date(value).toLocaleTimeString('zh-CN', {
  hour: '2-digit', minute: '2-digit', hour12: false,
});

export const dateOf = (value: string) => new Date(value).toLocaleString('zh-CN', {
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
});
