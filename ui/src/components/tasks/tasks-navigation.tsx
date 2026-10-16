import {useState} from 'react';
import {Button} from '@/components/ui/button';
import {Icon} from '@/components/chat/icon';
import type {TaskPage} from '@/types/tasks';
export function TasksNavigation({page,onNavigate}:{page:TaskPage|null;onNavigate:(page:TaskPage)=>void}){
 const [open,setOpen]=useState(true);
 return <nav className="chat-navigation" aria-label="TASKS"><h2 className="chat-section-title"><Button variant="ghost" className="chat-section-toggle" aria-controls="tasks-navigation" aria-expanded={open} onClick={()=>setOpen(v=>!v)}><span>TASKS</span><Icon name="chevron"/></Button></h2><ul id="tasks-navigation" className="chat-list" hidden={!open}>{(['Active Tasks','Task History','Scheduled Tasks'] as TaskPage[]).map(item=><li key={item}><Button variant="ghost" className="chat-link" aria-current={page===item?'page':undefined} onClick={()=>onNavigate(item)}>{item}</Button></li>)}</ul></nav>;
}
