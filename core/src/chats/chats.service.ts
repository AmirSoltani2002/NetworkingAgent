import { BadRequestException, ConflictException, Injectable, NotFoundException, ServiceUnavailableException } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { Express } from 'express';
import type { PoolClient } from 'pg';
import { DatabaseService } from '../database/database.service';
import type { ToolTrace } from '../llm/llm.service';
import { LlmService, ToolConfirmationRequired, ToolContinuationRequired, publicConfirmation } from '../llm/llm.service';
import type { ToolContinuation } from '../llm/llm.service';
import { checkContextSize, type ChatContextWindow } from '../llm/context-window';

interface ChatRow { id: string; title: string; createdAt: Date; updatedAt: Date }
interface MessageRow { id: string; text: string; role: string; createdAt: Date; replyToMessageId: string | null; toolCalls?:ToolTrace[]; toolState?:ToolContinuation; position?:string }
interface AttachmentRow { id: string; messageId: string; name: string; size: number }
const CHAT_FIELDS = 'id, title, created_at AS "createdAt", updated_at AS "updatedAt"';
const MESSAGE_FIELDS = 'id, text, role, created_at AS "createdAt", reply_to_message_id AS "replyToMessageId", tool_calls AS "toolCalls"';

@Injectable()
export class ChatsService {
  constructor(private readonly database: DatabaseService, private readonly llm: LlmService) {}

  async list() {
    const result = await this.database.pool.query<ChatRow>(`SELECT ${CHAT_FIELDS} FROM chats ORDER BY updated_at DESC, id`);
    return result.rows;
  }

  async create() {
    const result = await this.database.pool.query<ChatRow>(
      `INSERT INTO chats (id) VALUES ($1) RETURNING ${CHAT_FIELDS}`, [randomUUID()],
    );
    return result.rows[0];
  }

  async get(id: string) {
    return this.database.transaction(async client => {
      const chat = await this.findChat(client, id);
      const messages = await client.query<MessageRow>(
        `SELECT ${MESSAGE_FIELDS}, tool_state AS "toolState" FROM messages WHERE chat_id = $1 ORDER BY position`, [id],
      );
      const files = await client.query<AttachmentRow>(
        'SELECT a.id, a.message_id AS "messageId", a.name, a.size FROM attachments a JOIN messages m ON m.id = a.message_id WHERE m.chat_id = $1 ORDER BY m.position, a.position', [id],
      );
      const tasks=(await client.query('SELECT id,message_id FROM agent_tasks WHERE conversation_id=$1',[id])).rows;
      const task=tasks.find(t=>t.message_id===messages.rows.at(-1)?.id);
      return { ...chat, taskId:task?.id??null, pendingConfirmation:publicConfirmation(messages.rows.at(-1)?.toolState), messages: messages.rows.map(message => {
        const visible={...message}; delete visible.toolState;
        return {...visible,taskId:tasks.find(t=>t.message_id===message.id)?.id??null,attachments:files.rows.filter(file=>file.messageId===message.id).map(file=>this.fileMetadata(id,file))};
      }) };
    });
  }

  async addMessage(chatId: string, text: string, clientMessageId: string, files: Express.Multer.File[]) {
    if (!text.trim() && !files.length) throw new BadRequestException('Enter a message or attach a file.');
    if (text.length > 20000) throw new BadRequestException('Messages may contain up to 20,000 characters.');
    if (files.reduce((sum, file) => sum + file.size, 0) > 25 * 1024 * 1024) {
      throw new BadRequestException('Attachments may total up to 25 MB per message.');
    }

    return this.database.transaction(async client => {
      const lock = await client.query<{ acquired: boolean }>('SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0)) AS acquired', [chatId]);
      if (!lock.rows[0].acquired) throw new ConflictException('A response is already in progress for this chat. Wait and reopen the chat.');
      await this.findChat(client, chatId, true);
      const existing = await client.query<MessageRow>(
        `SELECT ${MESSAGE_FIELDS} FROM messages WHERE id = $1 AND chat_id = $2`, [clientMessageId, chatId],
      );
      if (!existing.rowCount) {
        // A new user turn invalidates any old unexecuted confirmation/continuation.
        await client.query('UPDATE messages SET tool_state=NULL WHERE chat_id=$1 AND tool_state IS NOT NULL',[chatId]);
        const previous = await client.query('SELECT id FROM messages WHERE chat_id = $1 LIMIT 1', [chatId]);
        await client.query('INSERT INTO messages (id, chat_id, text) VALUES ($1, $2, $3)', [clientMessageId, chatId, text.trim()]);
        for (const [position, file] of files.entries()) {
          const name = file.originalname.replace(/[\\/\r\n\0]/g, '_').slice(0, 255) || 'attachment';
          await client.query('INSERT INTO attachments (id, message_id, position, name, size, content) VALUES ($1, $2, $3, $4, $5, $6)',
            [randomUUID(), clientMessageId, position, name, file.size, file.buffer]);
        }
        const source = text.trim().replace(/\s+/g, ' ') || files[0]?.originalname || 'New chat';
        const characters = Array.from(source);
        const title = characters.length > 48 ? `${characters.slice(0, 47).join('')}…` : source;
        await client.query('UPDATE chats SET title = CASE WHEN $2 THEN $3 ELSE title END, updated_at = now() WHERE id = $1',
          [chatId, previous.rowCount === 0, title]);
      }
      const result = await client.query<MessageRow>(`SELECT ${MESSAGE_FIELDS} FROM messages WHERE id = $1 AND chat_id = $2`, [clientMessageId, chatId]);
      const attachments = await client.query<AttachmentRow>('SELECT id, message_id AS "messageId", name, size FROM attachments WHERE message_id = $1 ORDER BY position', [clientMessageId]);
      const chat = await this.findChat(client, chatId);
      return { chat, message: { ...result.rows[0], attachments: attachments.rows.map(file => this.fileMetadata(chatId, file)) } };
    });
  }

  async respond(chatId: string, messageId: string, decision?: {id:string;approved:boolean}) {
    const client = await this.database.pool.connect();
    let locked = false;
    let discard = false;
    try {
      const lock = await client.query<{ acquired: boolean }>('SELECT pg_try_advisory_lock(hashtextextended($1, 0)) AS acquired', [chatId]);
      locked = lock.rows[0].acquired;
      if (!locked) throw new ConflictException('A response is already in progress for this chat. Wait and reopen the chat.');
      await this.findChat(client, chatId);
      const target = await client.query<MessageRow>(`SELECT ${MESSAGE_FIELDS} FROM messages WHERE chat_id = $1 AND id = $2 AND role = 'user'`, [chatId, messageId]);
      if (!target.rowCount) throw new NotFoundException('User message not found in this chat.');
      const existing = await client.query<MessageRow>(`SELECT ${MESSAGE_FIELDS} FROM messages WHERE chat_id = $1 AND reply_to_message_id = $2`, [chatId, messageId]);
      if (existing.rowCount) return { chat: await this.findChat(client, chatId), message: { ...existing.rows[0], attachments: [] } };
      if ((await client.query('SELECT id FROM agent_tasks WHERE message_id=$1',[messageId])).rowCount) throw new ConflictException('This message belongs to a persistent task. Continue it in TASKS.');
      const history = await client.query<MessageRow>(`SELECT ${MESSAGE_FIELDS}, position::text AS position FROM messages WHERE chat_id = $1 ORDER BY position`, [chatId]);
      if (history.rows.at(-1)?.id !== messageId) throw new ConflictException('Only the latest unanswered message can receive a response.');
      const state=(await client.query<{state:ToolContinuation|null}>('SELECT tool_state AS state FROM messages WHERE id=$1',[messageId])).rows[0].state;
      if (state?.phase==='executing') throw new ConflictException('A confirmed tool may already have executed. Check its external status before requesting another operation; automatic replay is blocked.');
      if (decision && state?.pending?.id!==decision.id) throw new BadRequestException('This confirmation does not match the pending invocation.');
      if (!decision && state?.phase==='pending') return {chat:await this.findChat(client,chatId),pendingConfirmation:publicConfirmation(state)};
      // File bytes stay local; filenames explicitly tell the model that contents are unavailable.
      const files = await client.query<AttachmentRow>('SELECT a.message_id AS "messageId", a.name FROM attachments a JOIN messages m ON m.id = a.message_id WHERE m.chat_id = $1 ORDER BY m.position, a.position', [chatId]);
      const input = history.rows.map(message => {
        const names = files.rows.filter(file => file.messageId === message.id).map(file => file.name);
        return { role: message.role, content: message.text + (names.length
          ? `\n[Locally saved attachments; contents are not included: ${JSON.stringify(names)}]` : '') };
      });
      const context = (await client.query<{context:ChatContextWindow|null}>('SELECT context_window AS context FROM chats WHERE id=$1',[chatId])).rows[0].context;
      const newInput = context ? input.filter((_message,index)=>BigInt(history.rows[index].position!)>BigInt(context.throughPosition)) : input;
      let completedContext: {model:string;items:unknown[]} | undefined;
      const toolCalls: ToolTrace[] = [...(target.rows[0].toolCalls ?? [])];
      const saveState=async(value:ToolContinuation)=>{
        checkContextSize(value);
        const encoded=JSON.stringify(value);
        await client.query('UPDATE messages SET tool_state=$2::jsonb WHERE id=$1',[messageId,encoded]);
      };
      let text:string;
      try { text = await this.llm.respond(input, async trace => {
        toolCalls.push(trace);
        // Metadata/summary only; no credentials or full document passages.
        await client.query('UPDATE messages SET tool_calls=$2::jsonb WHERE id=$1',[messageId,JSON.stringify(toolCalls)]);
      },{state:state??undefined,decision,saveState,context,newInput,completeContext:async(model,items)=>{completedContext={model,items};}}); }
      catch(error) {
        if (error instanceof ToolContinuationRequired) {
          await saveState(error.state);
          if ((error.state.timeoutCount ?? 0)>=3) throw new ServiceUnavailableException('Three consecutive prompts timed out without progress. Completed work is saved; check OpenAI connectivity and retry.');
          return {chat:await this.findChat(client,chatId),continuation:{reason:error.reason}};
        }
        if (!(error instanceof ToolConfirmationRequired)) throw error;
        await saveState(error.state);
        return {chat:await this.findChat(client,chatId),pendingConfirmation:publicConfirmation(error.state)};
      }
      await client.query('BEGIN');
      try {
        const reply = await client.query<MessageRow>(`INSERT INTO messages (id, chat_id, role, text, reply_to_message_id, tool_calls) VALUES ($1, $2, 'assistant', $3, $4, $5::jsonb) RETURNING ${MESSAGE_FIELDS}, position::text AS position`,
          [randomUUID(), chatId, text, messageId, JSON.stringify(toolCalls)]);
        if (completedContext) {
          await client.query('UPDATE chats SET context_window=$2::jsonb WHERE id=$1',[chatId,JSON.stringify({...completedContext,throughPosition:reply.rows[0].position})]);
        }
        const chat = await client.query<ChatRow>(`UPDATE chats SET updated_at = now() WHERE id = $1 RETURNING ${CHAT_FIELDS}`, [chatId]);
        await client.query('UPDATE messages SET tool_state=NULL WHERE id=$1',[messageId]);
        await client.query('COMMIT');
        const visibleReply = {...reply.rows[0]}; delete visibleReply.position;
        return { chat: chat.rows[0], message: { ...visibleReply, attachments: [] } };
      } catch (error) {
        await client.query('ROLLBACK');
        throw error;
      }
    } finally {
      if (locked) {
        try { await client.query('SELECT pg_advisory_unlock(hashtextextended($1, 0))', [chatId]); }
        catch { discard = true; }
      }
      client.release(discard);
    }
  }

  async download(chatId: string, attachmentId: string) {
    const result = await this.database.pool.query<{ name: string; content: Buffer }>(
      'SELECT a.name, a.content FROM attachments a JOIN messages m ON m.id = a.message_id WHERE a.id = $1 AND m.chat_id = $2', [attachmentId, chatId],
    );
    if (!result.rowCount) throw new NotFoundException('Attachment not found.');
    return result.rows[0];
  }

  private async findChat(client: PoolClient, id: string, lock = false) {
    const result = await client.query<ChatRow>(`SELECT ${CHAT_FIELDS} FROM chats WHERE id = $1${lock ? ' FOR UPDATE' : ''}`, [id]);
    if (!result.rowCount) throw new NotFoundException('Chat not found.');
    return result.rows[0];
  }

  private fileMetadata(chatId: string, file: AttachmentRow) {
    return { id: file.id, name: file.name, size: file.size, downloadUrl: `/api/chats/${chatId}/attachments/${file.id}` };
  }
}
