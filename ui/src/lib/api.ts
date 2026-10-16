import type { ChatDetail, ChatMessage, ChatResponse, ChatSummary, PendingAttachment } from '@/types/chat';
import type { LlmConfiguration, LlmModels, Thinking } from '@/types/llm';

export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.message;
    throw new Error(typeof message === 'string' ? message : 'Could not complete the request. Please try again.');
  }
  return response.json();
}

export const chatApi = {
  list: (signal?: AbortSignal) => request<ChatSummary[]>('/api/chats', { signal }),
  create: () => request<ChatSummary>('/api/chats', { method: 'POST' }),
  get: (id: string, signal?: AbortSignal) => request<ChatDetail>(`/api/chats/${id}`, { signal }),
  respond: (id: string, messageId: string) => request<ChatResponse>(
    `/api/chats/${id}/messages/${messageId}/response`, { method: 'POST', cache: 'no-store' }),
  confirm:(id:string,messageId:string,confirmationId:string,approved:boolean)=>request<ChatResponse>(`/api/chats/${id}/messages/${messageId}/confirmation`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:confirmationId,approved}),cache:'no-store'}),
  send: (id: string, text: string, files: PendingAttachment[], clientMessageId: string) => {
    const body = new FormData();
    body.append('text', text);
    body.append('clientMessageId', clientMessageId);
    files.forEach(attachment => body.append('files', attachment.file));
    return request<{ chat: ChatSummary; message: ChatMessage }>(`/api/chats/${id}/messages`, { method: 'POST', body });
  },
};

export const llmApi = {
  get: (signal?: AbortSignal) => request<LlmConfiguration>('/api/llm', { signal, cache: 'no-store' }),
  models: (signal?: AbortSignal) => request<LlmModels>('/api/llm/models', { signal, cache: 'no-store' }),
  save: (values: { provider: 'openai'; apiKey?: string; model?: string; thinking?: Thinking }) =>
    request<LlmConfiguration>('/api/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    }),
};
