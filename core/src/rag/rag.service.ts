import { BadRequestException, ConflictException, HttpException, Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { DatabaseService } from '../database/database.service';
import { EnvironmentStore } from '../config/environment-store.service';
import { McpService, publicServer } from '../mcp/mcp.service';
import { approvedUrl, localRagOrigins } from '../mcp/network-policy';
import { ragRequest } from './rag-client';
import type { Express } from 'express';

@Injectable()
export class RagService {
  constructor(private readonly db: DatabaseService, private readonly env: EnvironmentStore, private readonly mcp: McpService) {}
  async list() {
    const values = await this.env.read();
    return (await this.mcp.list()).filter(row=>row.ragEnabled || !!row.restUrl).map(row => ({...row, hasCredential: !!(row.authEnvVar && values[row.authEnvVar])}));
  }
  private async configuration(body: unknown, id?: string) {
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new BadRequestException('Provide connection settings.');
    const input = body as Record<string,unknown>;
    if (Object.keys(input).some(key => !['name','url','restUrl','authentication','token'].includes(key))) throw new BadRequestException('Unsupported connection setting.');
    if (typeof input.name !== 'string' || !input.name.trim() || input.name.length > 100 || typeof input.url !== 'string' || typeof input.restUrl !== 'string' || !['none','bearer'].includes(String(input.authentication))) throw new BadRequestException('Enter a name, separate MCP and REST URLs, and authentication method.');
    const values = await this.env.read(); const origins = values.RAG_ALLOWED_ORIGINS ?? localRagOrigins;
    const url = approvedUrl(input.url,origins).href; const restUrl = approvedUrl(input.restUrl,origins).href;
    const existing = id ? await this.mcp.get(id) : undefined;
    if (input.token !== undefined && (typeof input.token !== 'string' || !/^[\x21-\x7e]{1,2048}$/.test(input.token))) throw new BadRequestException('Token must contain 1–2048 printable characters without spaces.');
    const secret = input.authentication === 'bearer' ? (input.token as string | undefined) ?? (existing?.auth_env_var ? values[existing.auth_env_var] : undefined) : undefined;
    if (input.authentication === 'bearer' && !secret) throw new BadRequestException('Enter a bearer token.');
    return { name: input.name.trim(), url, restUrl, secret, origins, existing, authentication:input.authentication, token: input.token as string | undefined };
  }
  async save(body: unknown, id?: string) {
    const value = await this.configuration(body,id);
    const serverId = id ?? randomUUID();
    const duplicate = (await this.mcp.list()).find(server => server.url === value.url && server.id !== serverId);
    if (duplicate) throw new ConflictException('This MCP endpoint already exists. Select its saved profile.');
    const auth = value.secret ? value.token ? await this.env.saveMcpToken(serverId,value.token) : value.existing?.auth_env_var : null;
    const saved = await this.mcp.save({ name:value.name,url:value.url,authEnvVar:auth },id,serverId);
    await this.db.pool.query(`UPDATE mcp_servers SET rag_enabled=true,rest_url=$2,rest_status='unconfigured',rest_error=NULL,disconnected=false,agent_enabled=false,updated_at=now() WHERE id=$1`,[saved.id,value.restUrl]);
    return (await this.list()).find(row => row.id === saved.id);
  }
  async test(body: unknown, id?: string) {
    const value = await this.configuration(body,id);
    const [mcp, rest] = await Promise.allSettled([this.mcp.inspect(value.url,value.secret), ragRequest({restUrl:value.restUrl,secret:value.secret,origins:value.origins},'api/devices?limit=1').then(result=>{if(!result||typeof result!=='object'||!('items' in result)||!Array.isArray(result.items)||!('total' in result)||typeof result.total!=='number')throw new BadRequestException('The REST API returned an incompatible device-list schema.');return result;})]);
    const result = { mcpStatus:mcp.status === 'fulfilled' ? 'connected' : 'failed', restStatus:rest.status === 'fulfilled' ? 'connected' : 'failed', tools:mcp.status === 'fulfilled' ? mcp.value.tools : [], serverName:mcp.status === 'fulfilled' ? mcp.value.serverName : null,
      mcpError:mcp.status === 'rejected' ? 'MCP connection failed. Check the endpoint, token and network.' : null, restError:rest.status === 'rejected' ? (rest.reason instanceof Error ? rest.reason.message : 'REST connectivity failed.') : null,
      retrievalAvailable:mcp.status === 'fulfilled' && mcp.value.tools.some(tool => tool.readOnly && /search|retriev/i.test(tool.name+' '+tool.description)) };
    // Testing drafts must not mark different saved endpoints as connected.
    if (id && value.existing?.url === value.url && value.existing.rest_url === value.restUrl && (!value.token) && value.authentication === (value.existing.auth_env_var ? 'bearer' : 'none')) {
      await this.db.pool.query(`UPDATE mcp_servers SET status=$2,rest_status=$3,tools=$4::jsonb,server_name=$5,last_error=$6,rest_error=$7,discovered_at=now(),disconnected=false,rag_enabled=true,allowed_tools=$8,updated_at=now() WHERE id=$1 AND url=$9 AND rest_url=$10 AND auth_env_var IS NOT DISTINCT FROM $11`,[id,result.mcpStatus,result.restStatus,JSON.stringify(result.tools),result.serverName,result.mcpError,result.restError,value.existing.allowed_tools.filter(name=>result.tools.some(tool=>tool.name===name&&tool.readOnly)),value.url,value.restUrl,value.existing.auth_env_var]);
    }
    return result;
  }
  async permissions(id: string, body: unknown) {
    const input = body as { allowedTools?: string[]; agentEnabled?: boolean };
    if (!input || typeof input.agentEnabled !== 'boolean' || Object.keys(input).some(key=>!['allowedTools','agentEnabled'].includes(key))) throw new BadRequestException('Choose tool permissions.');
    const row = await this.mcp.get(id);
    if (input.agentEnabled && (row.status !== 'connected' || row.disconnected)) throw new BadRequestException('Test the saved MCP connection before enabling retrieval.');
    await this.mcp.allow(id,{allowedTools:input.allowedTools});
    await this.db.pool.query('UPDATE mcp_servers SET agent_enabled=$2,rag_enabled=true WHERE id=$1',[id,input.agentEnabled]);
    return (await this.list()).find(row=>row.id===id);
  }
  async disconnect(id: string) { await this.mcp.get(id); await this.db.pool.query("UPDATE mcp_servers SET disconnected=true,agent_enabled=false,status='unconnected',rest_status='disconnected',updated_at=now() WHERE id=$1",[id]); return publicServer(await this.mcp.get(id)); }
  async request(id: string, path: string, method='GET', body?: unknown) {
    const row = await this.mcp.get(id); const values = await this.env.read();
    if (row.disconnected || !row.rest_url) throw new BadRequestException('Save and connect the RAG REST URL first.');
    const secret = row.auth_env_var ? values[row.auth_env_var] : undefined;
    if (row.auth_env_var && !secret) throw new BadRequestException('The saved bearer credential is missing.');
    try {
      const result = await ragRequest({restUrl:row.rest_url,secret,origins:values.RAG_ALLOWED_ORIGINS ?? localRagOrigins},path,method,body);
      await this.db.pool.query("UPDATE mcp_servers SET rest_status='connected',rest_error=NULL WHERE id=$1",[id]); return result;
    } catch(error) {
      if (!(error instanceof HttpException) || [401,403,503].includes(error.getStatus())) await this.db.pool.query("UPDATE mcp_servers SET rest_status='failed',rest_error='REST connection failed. Check the endpoint and authentication.' WHERE id=$1",[id]); throw error;
    }
  }
  async upload(id: string, file: Express.Multer.File | undefined, input: Record<string,string>) {
    if (!file || !file.size || file.size > 25*1024*1024 || !/\.(pdf|txt|md|markdown)$/i.test(file.originalname)) throw new BadRequestException('Select a nonempty PDF, TXT or Markdown file up to 25 MB.');
    const extension = file.originalname.split('.').at(-1)?.toLowerCase();
    if (extension === 'pdf' && file.buffer.subarray(0,5).toString() !== '%PDF-') throw new BadRequestException('The file is not a valid PDF.');
    if (extension !== 'pdf' && file.buffer.includes(0)) throw new BadRequestException('Text documents cannot contain binary data.');
    if (!input.title?.trim() || !input.document_type?.trim()) throw new BadRequestException('Document title and type are required.');
    const body = new FormData();
    for (const field of ['title','document_type','version','metadata','device_ids']) if (input[field] !== undefined) body.set(field,input[field]);
    const safeName = file.originalname.replace(/[\\/\r\n\0]/g,'_').slice(0,255);
    body.set('file',new Blob([new Uint8Array(file.buffer)],{type:extension==='pdf'?'application/pdf':extension==='txt'?'text/plain':'text/markdown'}),safeName);
    return this.request(id,'api/documents/upload','POST',body);
  }
}
