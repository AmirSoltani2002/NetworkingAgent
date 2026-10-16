import {useState} from 'react';
import {Button} from '@/components/ui/button';
import {Icon} from '@/components/chat/icon';
import type {RagPage} from '@/types/rag';
export const ragPages:RagPage[]=['Connection','Devices','Known Issues','Documents','Knowledge Search'];
export function RagNavigation({page,onNavigate}:{page:RagPage|null;onNavigate:(page:RagPage)=>void}) {
  const [open,setOpen]=useState(true);
  return <nav className="chat-navigation rag-navigation" aria-label="RAG"><h2 className="chat-section-title"><Button variant="ghost" className="chat-section-toggle" aria-expanded={open} aria-controls="rag-navigation" onClick={()=>setOpen(value=>!value)}><span>RAG</span><Icon name="chevron" /></Button></h2><ul id="rag-navigation" className="chat-list" hidden={!open}>{ragPages.map(item=><li key={item}><Button variant="ghost" className="chat-link" aria-current={page===item?'page':undefined} onClick={()=>onNavigate(item)}>{item}</Button></li>)}</ul></nav>;
}
