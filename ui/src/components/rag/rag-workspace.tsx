import {useEffect,useState} from 'react';
import type {RagConnection,RagPage} from '@/types/rag';
import {ragApi} from '@/lib/rag-api';
import {Connection} from './connection';
import {Management} from './management';
import {Action,Field,message} from './common';
export function RagWorkspace({page}:{page:RagPage}) {
 const [rows,setRows]=useState<RagConnection[]>([]),[selected,setSelected]=useState<string|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{const abort=new AbortController();ragApi.list(abort.signal).then(rows=>{setRows(rows);setSelected(rows[0]?.id??null);setLoading(false);}).catch(error=>{if(!abort.signal.aborted){setError(message(error));setLoading(false);}});return()=>abort.abort();},[]);
 const connection=rows.find(row=>row.id===selected)??null;
 function saved(row:RagConnection){setRows(current=>current.some(item=>item.id===row.id)?current.map(item=>item.id===row.id?row:item):[...current,row]);setSelected(row.id);}
 return <section className="rag-workspace"><div className="rag-page-heading"><div><p className="rag-eyebrow">RAG</p><h1>{page}</h1></div><div className="rag-profile"><Field label="Connection profile"><select value={selected??''} onChange={event=>setSelected(event.target.value||null)}><option value="">New connection</option>{rows.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></Field>{page==='Connection'&&<Action onClick={()=>setSelected(null)}>New</Action>}</div></div>{loading?<p role="status">Loading connections…</p>:error?<p role="alert" className="rag-error">{error}</p>:page==='Connection'?<Connection key={selected??'new'} connection={connection} onSaved={saved}/>:!connection||connection.disconnected||!connection.restUrl?<p className="rag-empty">Open RAG → Connection to save and connect the REST endpoint. MCP and REST can work independently.</p>:<Management key={selected+page} page={page} id={connection.id}/>}</section>;
}
