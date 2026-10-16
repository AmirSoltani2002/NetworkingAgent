import {FactoryWorkspace} from '@/components/factory/factory-workspace';
import type {FactoryPage} from '@/types/factory';
import {TasksWorkspace} from '@/components/tasks/tasks-workspace';
import {tasksApi} from '@/lib/tasks-api';
import type {TaskPage} from '@/types/tasks';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Composer } from '@/components/chat/composer';
import { Icon } from '@/components/chat/icon';
import { MessageList } from '@/components/chat/message-list';
import { RagWorkspace } from '@/components/rag/rag-workspace';
import {McpWorkspace} from '@/components/mcp/mcp-workspace';
import type {McpPage} from '@/types/mcp';
import type {PendingTool} from '@/types/chat';
import type { RagPage } from '@/types/rag';
import { Sidebar } from '@/components/chat/sidebar';
import { chatApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { ChatMessage, ChatSummary, PendingAttachment } from '@/types/chat';

export function App() {
  const [factoryPage,setFactoryPage]=useState<FactoryPage|null>(null);
  const [taskPage,setTaskPage]=useState<TaskPage|null>(null);
  const [taskDetailId,setTaskDetailId]=useState<string|null>(null);
  const [taskRevision,setTaskRevision]=useState(0);
  const [taskMode,setTaskMode]=useState(false);
  const [chatTaskId,setChatTaskId]=useState<string|null>(null);
  const [ragPage, setRagPage] = useState<RagPage | null>(null);
  const [mcpPage,setMcpPage]=useState<McpPage|null>(null);
  const [pending,setPending]=useState<PendingTool|null>(null);
  const [collapsed, setCollapsed] = useState(() => window.matchMedia('(max-width: 700px)').matches);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [saving, setSaving] = useState(false);
  const [responding, setResponding] = useState(false);
  const responsePending = useRef(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composerKey, setComposerKey] = useState(0);
  const request = useRef<AbortController | null>(null);
  const selected = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    chatApi.list(controller.signal).then(items => {
      if (!controller.signal.aborted) setChats(current => [...current, ...items.filter(item => !current.some(chat => chat.id === item.id))]);
    }).catch(error => {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Could not load chats.');
    });
    return () => { controller.abort(); request.current?.abort(); };
  }, []);

  useEffect(() => {
    if (!selectedId || typeof EventSource === 'undefined') return;
    const stream = new EventSource('/api/tasks/stream');
    const update = () => setTaskRevision(value => value + 1);
    stream.addEventListener('task', update);
    return () => stream.close();
  }, [selectedId]);

  function upsertChat(chat: ChatSummary) {
    setChats(current => [chat, ...current.filter(item => item.id !== chat.id)]);
  }

  function newChat() {
    setFactoryPage(null);setTaskPage(null);setChatTaskId(null);
    setMcpPage(null);setPending(null);
    setRagPage(null);
    request.current?.abort();
    selected.current = null;
    setSelectedId(null);
    setMessages([]);
    setLoading(false);
    setError(null);
    setComposerKey(value => value + 1);
    if (window.matchMedia('(max-width: 700px)').matches) setCollapsed(true);
  }

  async function selectChat(id: string) {
    setFactoryPage(null);setTaskPage(null);setChatTaskId(null);
    setMcpPage(null);setPending(null);
    setRagPage(null);
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    selected.current = id;
    setSelectedId(id);
    setMessages([]);
    setError(null);
    setLoading(true);
    setComposerKey(value => value + 1);
    if (window.matchMedia('(max-width: 700px)').matches) setCollapsed(true);
    try {
      const chat = await chatApi.get(id, controller.signal);
      if (!controller.signal.aborted) {setMessages(chat.messages);setChatTaskId(chat.taskId??null);setPending(chat.pendingConfirmation??null);}
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Could not load the chat.');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  async function sendMessage(text: string, files: PendingAttachment[], clientMessageId: string) {
    setSaving(true);
    setError(null);
    try {
      let id = selected.current;
      if (!id) {
        const chat = await chatApi.create();
        id = chat.id;
        selected.current = id;
        setSelectedId(id);
        upsertChat(chat);
      }
      const result = await chatApi.send(id, text, files, clientMessageId);
      upsertChat(result.chat);
      setMessages(current => current.some(item => item.id === result.message.id) ? current : [...current, result.message]);
      if(taskMode){const task=await tasksApi.create({conversationId:id,messageId:result.message.id,request:text});setChatTaskId(task.id);setMessages(current=>current.map(item=>item.id===result.message.id?{...item,taskId:task.id}:item));}
      else void generateResponse(id, result.message.id);
      return true;
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not save the message. Please try again.');
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function generateResponse(chatId: string, messageId: string, decision?:boolean) {
    if (responsePending.current) return;
    responsePending.current = true;
    setResponding(true);
    setError(null);
    try {
      let result = decision!==undefined&&pending?await chatApi.confirm(chatId,messageId,pending.id,decision):await chatApi.respond(chatId, messageId);
      let continuations = 0;
      while (result.continuation) {
        if (selected.current === chatId) setPending(null);
        if (continuations++ >= 20) throw new Error('Automatic continuation paused after 20 prompts. Completed work is saved; use Retry response to continue.');
        // Same saved user turn, a fresh per-prompt budget, and no synthetic chat messages.
        result = await chatApi.respond(chatId, messageId);
      }
      upsertChat(result.chat);
      if (selected.current === chatId) {
        const reply=result.message;
        if(reply)setMessages(current => current.some(item => item.id === reply.id) ? current : [...current, reply]);
        setPending(result.pendingConfirmation??null);
      }
    } catch (error) {
      if (selected.current === chatId) setError(error instanceof Error ? error.message : 'Could not get a response. Your message is saved; please retry.');
    } finally {
      responsePending.current = false;
      setResponding(false);
    }
  }

  const active = chats.find(chat => chat.id === selectedId);
  const latest = messages.at(-1);
  const retryMessageId = !saving && !loading && !pending && !chatTaskId && latest?.role === 'user' ? latest.id : null;
  const management=!!factoryPage||!!ragPage||!!mcpPage||!!taskPage;
  function navigateMcp(page:McpPage){setFactoryPage(null);setTaskPage(null);setRagPage(null);setMcpPage(page);if(window.matchMedia('(max-width: 700px)').matches)setCollapsed(true);}
  return (
    <div className={cn('app-shell', collapsed && 'sidebar-collapsed')}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(value => !value)} chats={chats}
        factoryPage={factoryPage} onFactory={page=>{setTaskPage(null);setRagPage(null);setMcpPage(null);setFactoryPage(page);if(window.matchMedia('(max-width: 700px)').matches)setCollapsed(true);}} taskPage={taskPage} onTasks={page=>{setFactoryPage(null);setTaskDetailId(null);setRagPage(null);setMcpPage(null);setTaskPage(page);if(window.matchMedia('(max-width: 700px)').matches)setCollapsed(true);}} mcpPage={mcpPage} onMcp={navigateMcp} ragPage={ragPage} onRag={page => {setFactoryPage(null);setTaskPage(null);setMcpPage(null);setRagPage(page); if (window.matchMedia('(max-width: 700px)').matches) setCollapsed(true);}} selectedId={management ? null : selectedId} busy={saving || responding} onNewChat={newChat} onSelect={id => void selectChat(id)} />
      <main className="main-panel" aria-label={factoryPage?'Factory simulation':taskPage?'Task management':ragPage ? 'RAG management' : mcpPage?'MCP management':'Chat'}>
        <header className="main-header">
          <Button variant="ghost" size="icon" className="icon-button reopen-sidebar" data-toggle-sidebar
            aria-label="Open sidebar" aria-expanded={!collapsed} onClick={() => setCollapsed(false)}>
            <Icon name="panel" />
          </Button>
          {!management && active && <span className="active-chat-title">{active.title}</span>}
        {management && <Button variant="ghost" className="rag-back" onClick={() => {setFactoryPage(null);setRagPage(null);setMcpPage(null);setTaskPage(null);}}>← Back to chat</Button>}
        </header>
        <div className="chat-view" hidden={management}>
        {error && <div className="assistant-message task-feedback" role="status">I couldn’t complete this request. {error}</div>}
        {loading && <p className="chat-loading" role="status">Loading chat…</p>}
        <MessageList taskRevision={taskRevision} onTask={id=>{setTaskDetailId(id);setTaskPage('Active Tasks');}} messages={messages} responding={responding} retryMessageId={retryMessageId} pending={pending} onDecide={approved=>{if(selectedId&&latest?.role==='user')void generateResponse(selectedId,latest.id,approved);}}
          onRetry={() => { if (selectedId && retryMessageId) void generateResponse(selectedId, retryMessageId); }} />
        <div className="task-chat-mode"><label><input type="checkbox" checked={taskMode} disabled={saving||responding} onChange={event=>setTaskMode(event.target.checked)}/> Run as task</label>{chatTaskId&&<Button variant="ghost" onClick={()=>{setTaskDetailId(chatTaskId);setTaskPage('Active Tasks');}}>View persistent task</Button>}</div>
        <Composer key={composerKey} onSend={sendMessage} busy={saving || loading || responding || !!pending} />
        </div>
        {factoryPage&&<FactoryWorkspace page={factoryPage} onTask={id=>{setFactoryPage(null);setTaskDetailId(id);setTaskPage('Active Tasks');}}/>}
        {taskPage&&<TasksWorkspace key={taskPage+taskDetailId} initialTaskId={taskDetailId} page={taskPage} onChat={id=>void selectChat(id)}/>}
        {ragPage && <RagWorkspace page={ragPage} />}
        {mcpPage&&<McpWorkspace page={mcpPage} onNavigate={navigateMcp}/>}
      </main>
    </div>
  );
}
