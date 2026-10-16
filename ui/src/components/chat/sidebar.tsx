import {FactoryNavigation} from '@/components/factory/factory-navigation';
import type {FactoryPage} from '@/types/factory';
import {TasksNavigation} from '@/components/tasks/tasks-navigation';
import type {TaskPage} from '@/types/tasks';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Icon } from './icon';
import { RagNavigation } from '@/components/rag/rag-navigation';
import {McpNavigation} from '@/components/mcp/mcp-navigation';
import type {McpPage} from '@/types/mcp';
import type { RagPage } from '@/types/rag';
import { LlmSettings } from '@/components/llm/llm-settings';
import type { ChatSummary } from '@/types/chat';

export function Sidebar({ collapsed, onToggle, chats, selectedId, busy, onNewChat, onSelect, ragPage, onRag, mcpPage, onMcp, taskPage, onTasks, factoryPage, onFactory }: {
  factoryPage:FactoryPage|null;
  onFactory:(page:FactoryPage)=>void;
  taskPage:TaskPage|null;
  onTasks:(page:TaskPage)=>void;
  mcpPage:McpPage|null;
  onMcp:(page:McpPage)=>void;
  ragPage: RagPage | null;
  onRag: (page: RagPage) => void;
  collapsed: boolean;
  onToggle: () => void;
  chats: ChatSummary[];
  selectedId: string | null;
  busy: boolean;
  onNewChat: () => void;
  onSelect: (id: string) => void;
}) {
  const [chatsOpen, setChatsOpen] = useState(true);

  return (
    <aside className="sidebar" aria-label="Sidebar">
      <header className="sidebar-header">
        <span className="brand">Meta-Harness</span>
        <Button variant="ghost" size="icon" className="icon-button" data-toggle-sidebar
          aria-label="Close sidebar" aria-expanded={!collapsed} onClick={onToggle}>
          <Icon name="panel" />
        </Button>
      </header>
      <div className="sidebar-content">
        <Button variant="ghost" className="new-chat" onClick={onNewChat} disabled={busy}>
          <Icon name="plus" />New chat
        </Button>
        <nav className="chat-navigation" aria-label="Chats">
          <h2 className="chat-section-title">
            <Button variant="ghost" className="chat-section-toggle" aria-expanded={chatsOpen}
              aria-controls="chat-titles" onClick={() => setChatsOpen(open => !open)}>
              <span>Chats</span><Icon name="chevron" />
            </Button>
          </h2>
          <div id="chat-titles" hidden={!chatsOpen}>
            <ul className="chat-list">
              {chats.map(chat => (
                <li key={chat.id}>
                  <Button variant="ghost" className="chat-link" aria-current={selectedId === chat.id ? 'page' : undefined}
                    title={chat.title} onClick={() => onSelect(chat.id)} disabled={busy}>
                    <span>{chat.title}</span>
                  </Button>
                </li>
              ))}
            </ul>
            {!chats.length && <p className="empty-chats">Your chats will appear here.</p>}
          </div>
        </nav>
        <LlmSettings />
        <RagNavigation page={ragPage} onNavigate={onRag} />
        <McpNavigation page={mcpPage} onNavigate={onMcp}/>
        <FactoryNavigation page={factoryPage} onNavigate={onFactory}/>
        <TasksNavigation page={taskPage} onNavigate={onTasks}/>
      </div>
    </aside>
  );
}
