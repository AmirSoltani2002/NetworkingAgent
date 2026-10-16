import type {McpTool} from './rag';
export type McpPage='Connections'|'Add MCP Server';
export interface McpConnection {id:string;name:string;description:string;url:string;authEnvVar:string|null;hasCredential:boolean;enabled:boolean;agentEnabled:boolean;tools:McpTool[];allowedTools:string[];status:string;disconnected:boolean;lastError:string|null;discoveredAt:string|null;serverName:string|null;ragEnabled:boolean}
export interface McpInput {name:string;description:string;url:string;authentication:'none'|'bearer';token?:string;authEnvVar?:string;enabled:boolean}
export interface McpTest {status:string;tools:McpTool[];serverName:string|null;discoveredAt:string;lastError:string|null}
