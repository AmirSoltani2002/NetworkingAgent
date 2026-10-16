import {useState} from 'react';
import {Button} from '@/components/ui/button';
import {Icon} from '@/components/chat/icon';
import type {FactoryPage} from '@/types/factory';
export function FactoryNavigation({page,onNavigate}:{page:FactoryPage|null;onNavigate:(p:FactoryPage)=>void}){
 const [open,setOpen]=useState(true);
 return <nav className="chat-navigation" aria-label="FACTORY"><h2 className="chat-section-title"><Button variant="ghost" className="chat-section-toggle" aria-expanded={open} aria-controls="factory-navigation" onClick={()=>setOpen(v=>!v)}><span>FACTORY</span><Icon name="chevron"/></Button></h2><ul id="factory-navigation" className="chat-list" hidden={!open}>{(['Factory Simulation','Machine Monitoring','Alarms','Simulation Settings'] as FactoryPage[]).map(p=><li key={p}><Button variant="ghost" className="chat-link" aria-current={page===p?'page':undefined} onClick={()=>onNavigate(p)}>{p}</Button></li>)}</ul></nav>;
}
