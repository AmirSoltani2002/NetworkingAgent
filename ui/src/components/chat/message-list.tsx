import { Fragment, useEffect, useRef, useState } from 'react';
import type { ChatMessage,PendingTool } from '@/types/chat';
import { AttachmentCard } from './attachment-card';
import { TaskFeedback } from './task-feedback';
import { Button } from '@/components/ui/button';

export function MessageList({ messages, responding, retryMessageId, onRetry, pending, onDecide, taskRevision, onTask }: {
  taskRevision?: number;
  onTask?: (id:string)=>void;
  pending?:PendingTool|null;
  onDecide?:(approved:boolean)=>void;
  messages: ChatMessage[];
  responding: boolean;
  retryMessageId: string | null;
  onRetry: () => void;
}) {
  const conversation = useRef<HTMLElement>(null);
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{if(!pending)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[pending]);
  useEffect(() => {
    if (conversation.current) conversation.current.scrollTop = conversation.current.scrollHeight;
  }, [messages, responding, retryMessageId]);

  return (
    <section ref={conversation} className="conversation" aria-label="Conversation" aria-live="polite">
      <div className="messages">
        {messages.map(message => (
          <Fragment key={message.id}><article className={message.role === 'assistant' ? 'assistant-message' : 'user-message'}
            aria-label={message.role === 'assistant' ? 'Assistant response' : 'Your message'}>
            {message.attachments.length > 0 && (
              <ul className="message-attachments" aria-label="Message attachments">
                {message.attachments.map(attachment => (
                  <li key={attachment.id}>
                    <AttachmentCard file={attachment} downloadUrl={attachment.downloadUrl} />
                  </li>
                ))}
              </ul>
            )}
            {message.text && <p className="message-text">{message.text}</p>}
            {!!message.toolCalls?.length && (message.role==='assistant'||!messages.some(reply=>reply.replyToMessageId===message.id)) && <details className="tool-trace"><summary>Tool activity · {message.toolCalls.length} tool calls</summary>{message.toolCalls.map((call,index)=><div key={index}><p>{call.tool} · {call.success?'Completed':'Failed'} · {call.durationMs} ms</p><small>Server: {call.serverId}</small>{call.sources.map((source,index)=><p key={index}>{source.document_title ?? source.document_id}{source.page_number!==undefined?` · Page ${source.page_number}`:''}<small>Chunk: {source.chunk_id}</small></p>)}{call.result!==undefined&&<details><summary>Structured result summary</summary><pre>{JSON.stringify(call.result,null,2)}</pre></details>}</div>)}</details>}
          </article>
          {message.taskId&&<TaskFeedback taskId={message.taskId} revision={taskRevision??0} hasReply={messages.some(reply=>reply.replyToMessageId===message.id)} onOpen={()=>onTask?.(message.taskId!)} />}
          </Fragment>
        ))}
        {pending&&<section className="tool-confirmation" aria-label="Tool confirmation"><h2>Confirm tool operation</h2><p>“{pending.serverName}” may change data or model state. Review this invocation before running it.</p><dl><dt>Tool</dt><dd>{pending.tool}</dd></dl><details open><summary>Arguments</summary><pre>{JSON.stringify(pending.arguments,null,2)}</pre></details>{Date.parse(pending.expiresAt)<now&&<p>This confirmation expired. Decline it or start a new chat.</p>}<div className="rag-actions"><Button disabled={responding||Date.parse(pending.expiresAt)<now} onClick={()=>onDecide?.(true)}>Confirm and run</Button><Button variant="outline" disabled={responding} onClick={()=>onDecide?.(false)}>Decline</Button></div></section>}
        {responding && <p className="response-status" role="status">Responding…</p>}
        {!responding && retryMessageId && <Button type="button" variant="secondary" className="retry-response" onClick={onRetry}>Retry response</Button>}
      </div>
    </section>
  );
}
