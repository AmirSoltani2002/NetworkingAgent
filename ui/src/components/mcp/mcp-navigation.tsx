import {useState} from 'react';
import {Button} from '@/components/ui/button';
import {Icon} from '@/components/chat/icon';
import type {McpPage} from '@/types/mcp';
export function McpNavigation({page,onNavigate}:{page:McpPage|null;onNavigate:(page:McpPage)=>void}) {
 const [open,setOpen]=useState(true);
 return <nav className="chat-navigation" aria-label="MCP"><h2 className="chat-section-title"><Button variant="ghost" className="chat-section-toggle" aria-controls="mcp-navigation" aria-expanded={open} onClick={()=>setOpen(value=>!value)}><span>MCP</span><Icon name="chevron"/></Button></h2><ul id="mcp-navigation" className="chat-list" hidden={!open}>{(['Connections','Add MCP Server'] as McpPage[]).map(item=><li key={item}><Button variant="ghost" className="chat-link" aria-current={page===item?'page':undefined} onClick={()=>onNavigate(item)}>{item}</Button></li>)}</ul></nav>;
}
