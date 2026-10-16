export interface PendingAttachment {
  id: string;
  file: File;
}

export interface SentAttachment {
  id: string;
  name: string;
  size: number;
  downloadUrl: string;
}

export interface ChatMessage {
  taskId?: string | null;
  id: string;
  role: 'user' | 'assistant';
  replyToMessageId: string | null;
  text: string;
  attachments: SentAttachment[];
  toolCalls?: {serverId:string;tool:string;success:boolean;durationMs:number;result?:unknown;sources:{chunk_id?:string;document_id?:string;document_title?:string;page_number?:number}[]}[];
}

export interface ChatSummary {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface ChatDetail extends ChatSummary {
  taskId?:string|null;
  messages: ChatMessage[];
  pendingConfirmation?:PendingTool|null;
}
export interface PendingTool {id:string;serverId:string;serverName:string;tool:string;arguments:Record<string,unknown>;expiresAt:string}
export interface ChatResponse {chat:ChatSummary;message?:ChatMessage;pendingConfirmation?:PendingTool|null;continuation?:{reason:'tool_calls'|'model_turns'|'deadline'}}
