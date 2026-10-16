import { BadRequestException, ConflictException, Injectable, Logger, NotFoundException, ServiceUnavailableException } from '@nestjs/common';
import { randomUUID, createHash } from 'node:crypto';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { DatabaseService } from '../database/database.service';
import { EnvironmentStore } from '../config/environment-store.service';
import { approvedUrl, guardedFetch, mcpOrigins } from './network-policy';
import Ajv from 'ajv';

export interface Tool { name: string; description: string; readOnly: boolean; inputSchema: Record<string, unknown> }
export interface Server { id: string; name: string; url: string; auth_env_var: string | null; tools: Tool[]; allowed_tools: string[]; status: string; last_error: string | null; discovered_at: string | null; updated_at: string; rest_url?: string | null; rest_status?: string; rest_error?: string | null; rag_enabled?: boolean; agent_enabled?: boolean; disconnected?: boolean; server_name?: string | null; description?: string; enabled?: boolean }
const columns = 'id,name,url,auth_env_var,tools,allowed_tools,status,last_error,discovered_at,updated_at,rest_url,rest_status,rest_error,rag_enabled,agent_enabled,disconnected,server_name,description,enabled';
export function publicServer(row: Server) {
  return { id: row.id, name: row.name, url: row.url, authEnvVar: row.auth_env_var, tools: row.tools,
    allowedTools: row.allowed_tools, status: row.status, lastError: row.last_error, discoveredAt: row.discovered_at, updatedAt: row.updated_at, restUrl: row.rest_url ?? null, restStatus: row.rest_status ?? 'unconfigured', restError: row.rest_error ?? null, ragEnabled: !!row.rag_enabled, agentEnabled: !!row.agent_enabled, disconnected: !!row.disconnected, serverName: row.server_name ?? null, description: row.description ?? '', enabled: row.enabled !== false };
}
export function validateMcpConfiguration(body: unknown) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new BadRequestException('Provide a server name and Streamable HTTP URL.');
  const input = body as Record<string, unknown>;
  if (Object.keys(input).some(key => !['name', 'url', 'authEnvVar'].includes(key))) throw new BadRequestException('Unsupported MCP setting.');
  if (typeof input.name !== 'string' || !input.name.trim() || input.name.length > 100 || typeof input.url !== 'string' || input.url.length > 2048) throw new BadRequestException('Invalid server name or URL.');
  let url: URL;
  try { url = new URL(input.url); } catch { throw new BadRequestException('Use an absolute HTTP or HTTPS URL.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new BadRequestException('MCP URL must use HTTP(S), without credentials, query parameters, or fragments.');
  const auth = input.authEnvVar === '' || input.authEnvVar === undefined || input.authEnvVar === null ? null : input.authEnvVar;
  if (auth !== null && (typeof auth !== 'string' || !/^[A-Z][A-Z0-9_]{0,127}$/.test(auth))) throw new BadRequestException('Use an environment-variable name for bearer authentication.');
  return { name: input.name.trim(), url: url.href, auth: auth as string | null };
}

@Injectable()
export class McpService {
  constructor(private readonly db: DatabaseService, private readonly environment: EnvironmentStore) {}
  private readonly logger = new Logger(McpService.name);
  async onApplicationBootstrap() {
    const rows = (await this.list()).filter(row=>row.enabled && row.agentEnabled && !row.disconnected);
    for (const row of rows) {
      try { await this.discover(row.id); }
      catch { this.logger.warn(JSON.stringify({event:'mcp_reconnect_failed',serverId:row.id})); }
    }
  }
  async managedList() {
    const values = await this.environment.read();
    return (await this.list()).map(row=>({...row,hasCredential:!!(row.authEnvVar && values[row.authEnvVar])}));
  }
  private async managedConfiguration(body: unknown, id?: string) {
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new BadRequestException('Provide MCP connection settings.');
    const input = body as Record<string,unknown>;
    if (Object.keys(input).some(key=>!['name','description','url','authentication','token','authEnvVar','enabled'].includes(key))
      || typeof input.description !== 'string' || input.description.length>2000 || typeof input.enabled !== 'boolean'
      || !['none','bearer'].includes(String(input.authentication))) throw new BadRequestException('Enter a description, enabled state and supported authentication method.');
    const value = validateMcpConfiguration({name:input.name,url:input.url,authEnvVar:input.authEnvVar});
    const values = await this.environment.read();
    approvedUrl(value.url,mcpOrigins(values));
    const existing = id ? await this.get(id) : undefined;
    if (input.token !== undefined && (typeof input.token !== 'string' || !/^[\x21-\x7e]{1,2048}$/.test(input.token))) throw new BadRequestException('Token must contain 1–2048 printable characters without spaces.');
    const auth = input.authentication === 'bearer' ? value.auth ?? existing?.auth_env_var ?? null : null;
    const secret = input.authentication === 'bearer' ? (input.token as string|undefined) ?? (auth ? values[auth] : undefined) : undefined;
    if (input.authentication === 'bearer' && !secret) throw new BadRequestException('Enter a bearer token or reference a configured root .env credential.');
    return { ...value, description:input.description.trim(), enabled:input.enabled, secret, auth,
      token:input.token as string|undefined, existing };
  }
  async managedSave(body: unknown, id?: string) {
    const value = await this.managedConfiguration(body,id); const serverId = id ?? randomUUID();
    if ((await this.list()).some(row=>row.url===value.url && row.id!==serverId)) throw new ConflictException('This MCP URL is already registered. Edit its existing connection.');
    const auth = value.token ? await this.environment.saveMcpToken(serverId,value.token) : value.auth;
    await this.save({name:value.name,url:value.url,authEnvVar:auth},id,serverId);
    await this.db.pool.query('UPDATE mcp_servers SET description=$2,enabled=$3,disconnected=false,updated_at=now() WHERE id=$1',[serverId,value.description,value.enabled]);
    return (await this.managedList()).find(row=>row.id===serverId);
  }
  async managedTest(body: unknown, id?: string) {
    const value = await this.managedConfiguration(body,id);
    try {
      if (id && !value.token && value.existing?.url===value.url && value.existing.auth_env_var===value.auth) return this.discover(id);
      return { ...(await this.inspect(value.url,value.secret)), status:'connected', lastError:null, discoveredAt:new Date().toISOString() };
    } catch { throw new ServiceUnavailableException('MCP connection failed. Check the endpoint, authentication and approved origin.'); }
  }
  async permissions(id: string, body: unknown) {
    const input=body as {allowedTools?:string[];enabled?:boolean};
    if (!input || typeof input.enabled!=='boolean' || Object.keys(input).some(key=>!['allowedTools','enabled'].includes(key))) throw new BadRequestException('Choose enabled state and explicit tool permissions.');
    const row=await this.get(id);
    if (input.enabled && (row.status!=='connected' || row.disconnected)) throw new BadRequestException('Test the saved connection before enabling tools.');
    await this.allow(id,{allowedTools:input.allowedTools},false);
    await this.db.pool.query('UPDATE mcp_servers SET enabled=$2,agent_enabled=$3,updated_at=now() WHERE id=$1',[id,input.enabled,input.enabled && !!input.allowedTools?.length]);
    return (await this.managedList()).find(row=>row.id===id);
  }
  async disconnect(id: string) {
    await this.get(id);
    await this.db.pool.query("UPDATE mcp_servers SET disconnected=true,agent_enabled=false,status='unconnected',rest_status=CASE WHEN rag_enabled THEN 'disconnected' ELSE rest_status END,updated_at=now() WHERE id=$1",[id]);
    return (await this.managedList()).find(row=>row.id===id);
  }
  async list() { return (await this.db.pool.query<Server>(`SELECT ${columns} FROM mcp_servers ORDER BY created_at,id`)).rows.map(publicServer); }
  async get(id: string) {
    const row = (await this.db.pool.query<Server>(`SELECT ${columns} FROM mcp_servers WHERE id=$1`, [id])).rows[0];
    if (!row) throw new NotFoundException('MCP server not found.');
    return row;
  }
  async save(body: unknown, id?: string, newId?: string) {
    const value = validateMcpConfiguration(body);
    approvedUrl(value.url, mcpOrigins(await this.environment.read()));
    if (id) await this.get(id);
    try {
      const result = id ? await this.db.pool.query<Server>(`UPDATE mcp_servers SET name=$2::varchar,url=$3::varchar,auth_env_var=$4::varchar,
        tools=CASE WHEN url=$3::varchar AND auth_env_var IS NOT DISTINCT FROM $4::varchar THEN tools ELSE '[]'::jsonb END,
        allowed_tools=CASE WHEN url=$3::varchar AND auth_env_var IS NOT DISTINCT FROM $4::varchar THEN allowed_tools ELSE '{}'::text[] END,
        status='unconnected',agent_enabled=false,last_error=NULL,discovered_at=NULL,updated_at=now() WHERE id=$1 RETURNING ${columns}`,
        [id,value.name,value.url,value.auth]) : await this.db.pool.query<Server>(`INSERT INTO mcp_servers(id,name,url,auth_env_var)
        VALUES($1,$2,$3,$4) RETURNING ${columns}`, [newId ?? randomUUID(),value.name,value.url,value.auth]);
      return publicServer(result.rows[0]);
    } catch (error) {
      if (error && typeof error === 'object' && 'code' in error && error.code === '23505') throw new ConflictException('This MCP URL is already registered.');
      throw error;
    }
  }
  async remove(id: string) { await this.get(id); await this.db.pool.query('DELETE FROM mcp_servers WHERE id=$1', [id]); return { deleted: true }; }
  async allow(id: string, body: unknown, readOnlyOnly = true) {
    const row = await this.get(id);
    const input = body as { allowedTools?: unknown } | null;
    if (!input || Object.keys(input).some(key => key !== 'allowedTools') || !Array.isArray(input.allowedTools) || input.allowedTools.length > 500
      || input.allowedTools.some(name => typeof name !== 'string' || !row.tools.some(tool => tool.name === name && (!readOnlyOnly || tool.readOnly)))) throw new BadRequestException(readOnlyOnly ? 'Only discovered tools marked read-only can be allowlisted.' : 'Only discovered tools can be allowlisted.');
    const result = await this.db.pool.query<Server>(`UPDATE mcp_servers SET allowed_tools=$2,updated_at=now() WHERE id=$1 RETURNING ${columns}`, [id,[...new Set(input.allowedTools)]]);
    return publicServer(result.rows[0]);
  }
  async inspect(url: string, secret?: string) {
    if (secret && /[\r\n]/.test(secret)) throw new BadRequestException('Bearer credential must be a single line.');
    const values = await this.environment.read();
    const network = guardedFetch(url,mcpOrigins(values));
    const abort = new AbortController(); const timer = setTimeout(() => abort.abort(),15000);
    const client = new Client({ name: 'local-meta-harness', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(url), { fetch: network, requestInit: { signal: abort.signal, headers: secret ? { Authorization: `Bearer ${secret}` } : {} } });
    try {
      await client.connect(transport);
      const tools: Tool[] = []; let bytes = 0; let cursor: string | undefined;
      const scrub = (text: string) => secret ? text.split(secret).join('[redacted]') : text;
      do {
        const result = await client.listTools(cursor ? { cursor } : undefined, { timeout: 10000, signal: abort.signal });
        for (const tool of result.tools) {
          bytes += Buffer.byteLength(JSON.stringify(tool));
          if (tools.length >= 500 || bytes > 2*1024*1024 || tool.name.length > 200 || Buffer.byteLength(JSON.stringify(tool.inputSchema)) > 65536) throw new Error();
          tools.push({ name: scrub(tool.name), description: scrub(tool.description ?? '').slice(0,2000), readOnly: tool.annotations?.readOnlyHint === true, inputSchema: JSON.parse(scrub(JSON.stringify(tool.inputSchema))) });
        }
        cursor = result.nextCursor;
      } while (cursor);
      return { tools, serverName: scrub(client.getServerVersion()?.name ?? '').slice(0,200) };
    } catch { throw new ServiceUnavailableException('MCP discovery failed. Check the URL, authentication and server network.'); }
    finally { clearTimeout(timer); abort.abort(); await client.close().catch(() => undefined); }
  }
  async discover(id: string) {
    const row = await this.get(id);
    const values = await this.environment.read();
    const secret = row.auth_env_var ? values[row.auth_env_var] : undefined;
    if (row.auth_env_var && !secret) throw new BadRequestException('The referenced credential is missing from the root .env.');
    try {
      const { tools, serverName } = await this.inspect(row.url,secret);
      const result = await this.db.pool.query<Server>(`UPDATE mcp_servers SET tools=$2::jsonb,
        allowed_tools=$3,status='connected',disconnected=false,last_error=NULL,discovered_at=now(),server_name=$6,updated_at=now()
        WHERE id=$1 AND url=$4 AND auth_env_var IS NOT DISTINCT FROM $5 RETURNING ${columns}`,
        [id,JSON.stringify(tools),row.allowed_tools.filter(name => tools.some(tool => tool.name === name)),row.url,row.auth_env_var,serverName]);
      if (!result.rows[0]) throw new ConflictException('Server settings changed. Discover tools again.');
      return publicServer(result.rows[0]);
    } catch (error) {
      if (error instanceof ConflictException) throw error;
      await this.db.pool.query(`UPDATE mcp_servers SET status='failed',last_error=$2,updated_at=now() WHERE id=$1 AND url=$3::varchar AND auth_env_var IS NOT DISTINCT FROM $4::varchar`,[id,'MCP connection failed. Check the URL, authentication and server network.',row.url,row.auth_env_var]);
      throw new ServiceUnavailableException('MCP discovery failed. Check the URL, authentication and server network.');
    }
  }

  async agentTools() {
    const rows = (await this.db.pool.query<Server>(`SELECT ${columns} FROM mcp_servers WHERE enabled AND agent_enabled AND NOT disconnected AND status='connected' ORDER BY id`)).rows;
    return rows.flatMap(row => row.tools.filter(tool => row.allowed_tools.includes(tool.name)).map(tool => ({
      serverId: row.id, serverName: row.name, toolName: tool.name, readOnly: tool.readOnly, type: 'function' as const,
      name: `mcp_${createHash('sha256').update(row.id + ':' + tool.name).digest('hex').slice(0,24)}`,
      description: `${row.name}. ${(row.description ?? '').slice(0,500)}. ${tool.name}: ${tool.description.slice(0,1600)}${tool.readOnly ? '' : ' Requires explicit user confirmation before execution.'}`.slice(0,2400), parameters: tool.inputSchema, strict: false,
    }))).slice(0,64);
  }

  async prepareCall(serverId: string, toolName: string, args: unknown) {
    const row = await this.get(serverId);
    const tool = row.tools.find(tool => tool.name === toolName);
    if (row.enabled === false || !row.agent_enabled || row.disconnected || row.status !== 'connected' || !row.allowed_tools.includes(toolName) || !tool) throw new BadRequestException('Tool is not permitted for chat.');
    try {
      if (/"(?:pattern|patternProperties)"\s*:/.test(JSON.stringify(tool.inputSchema))) throw new Error();
      const validator = new Ajv({ strict: false, validateFormats: false }).compile(tool.inputSchema);
      if (!validator(args) || !args || typeof args !== 'object' || Array.isArray(args) || Buffer.byteLength(JSON.stringify(args)) > 65536) throw new Error();
    } catch { throw new BadRequestException('Invalid MCP tool arguments or unsupported input schema.'); }
    const configurationDigest = createHash('sha256').update(JSON.stringify([row.url,row.auth_env_var,row.updated_at,row.allowed_tools,tool])).digest('hex');
    return { serverId, serverName: row.name, toolName, readOnly: tool.readOnly, url:row.url, authEnvVar:row.auth_env_var, configurationDigest, argumentsDigest: createHash('sha256').update(JSON.stringify(args)).digest('hex') };
  }

  async execute(serverId: string, toolName: string, args: unknown, parentSignal?: AbortSignal, confirmation?: {configurationDigest:string;argumentsDigest:string}, execution?: {operationId:string;beforeDispatch:()=>Promise<void>}) {
    const prepared = await this.prepareCall(serverId,toolName,args);
    if (!prepared.readOnly && (!confirmation || confirmation.configurationDigest !== prepared.configurationDigest || confirmation.argumentsDigest !== prepared.argumentsDigest)) throw new BadRequestException('Explicit confirmation is required for this exact state-changing invocation.');
    const values = await this.environment.read();
    const secret = prepared.authEnvVar ? values[prepared.authEnvVar] : undefined;
    if (prepared.authEnvVar && !secret) throw new BadRequestException('The referenced credential is missing from the root .env.');
    const network = guardedFetch(prepared.url,mcpOrigins(values));
    const abort = new AbortController(); const signal = parentSignal ? AbortSignal.any([abort.signal,parentSignal]) : abort.signal; const timer = setTimeout(() => abort.abort(),20000);
    const client = new Client({ name: 'local-meta-harness', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(prepared.url), { fetch: network, requestInit: { signal, headers: { ...(secret ? { Authorization: `Bearer ${secret}` } : {}), ...(execution ? {'Idempotency-Key':execution.operationId} : {}) } } });
    let dispatched=false;
    const started = Date.now();
    try {
      await client.connect(transport);
      const current=await this.prepareCall(serverId,toolName,args);
      if(current.configurationDigest!==prepared.configurationDigest) throw new BadRequestException('MCP settings or permissions changed before execution.');
      await execution?.beforeDispatch();dispatched=true;
      const output = await client.callTool({ name: toolName, arguments: args as Record<string, unknown>, ...(execution ? {_meta:{operationId:execution.operationId}} : {}) }, undefined, { timeout: 15000, signal });
      let encoded = JSON.stringify(output);
      if (Buffer.byteLength(encoded) > 256 * 1024) throw new Error('Tool output exceeds limit');
      for (const [name,value] of Object.entries(values)) if (/(KEY|TOKEN|PASSWORD)/.test(name) && value && value.length >= 8) encoded = encoded.split(value).join('[redacted]');
      const result = JSON.parse(encoded);
      this.logger.log(JSON.stringify({ event: 'mcp_call', serverId, tool: toolName, durationMs: Date.now()-started, success: !result.isError }));
      return result as Record<string, unknown>;
    } catch (cause) {
      this.logger.warn(JSON.stringify({ event: 'mcp_call', serverId, tool: toolName, durationMs: Date.now()-started, success: false }));
      await this.db.pool.query("UPDATE mcp_servers SET status='failed',last_error='MCP connection failed. Test the connection again.',updated_at=now() WHERE id=$1",[serverId]);
      const error=new ServiceUnavailableException('MCP tool execution failed. Test the connection again.');
      const status=Number((cause as {code?:number;status?:number})?.status??(cause as {code?:number})?.code);
      Object.assign(error,{outcomeUnknown:dispatched&&!prepared.readOnly,dispatched,permanent:[400,401,403,404,405,422].includes(status)});throw error;
    } finally { clearTimeout(timer); abort.abort(); await client.close().catch(() => undefined); }
  }

}
