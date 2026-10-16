export type RagPage = 'Connection' | 'Devices' | 'Known Issues' | 'Documents' | 'Knowledge Search';
export interface McpTool {name:string;description:string;readOnly:boolean;inputSchema:Record<string,unknown>}
export interface RagConnection { id:string;name:string;url:string;restUrl:string|null;authEnvVar:string|null;hasCredential:boolean;tools:McpTool[];allowedTools:string[];status:string;restStatus:string;lastError:string|null;restError:string|null;serverName:string|null;disconnected:boolean;agentEnabled:boolean }
export interface ConnectionInput {name:string;url:string;restUrl:string;authentication:'none'|'bearer';token?:string}
export interface ConnectionTest {mcpStatus:string;restStatus:string;mcpError:string|null;restError:string|null;tools:McpTool[];serverName:string|null;retrievalAvailable:boolean}
export interface Device {id:string;name:string;model:string;manufacturer:string;description:string;metadata:Record<string,unknown>}
export interface Issue {id:string;device_id:string;title:string;category:string;symptoms:string;possible_cause:string;description:string}
export interface DocumentRecord {id:string;title:string;document_type:string;version:string;status:string;created_at:string;device_ids:string[];metadata:Record<string,unknown>}
export interface Chunk {chunk_id:string;document_id:string;document_title:string;content:string;section_heading:string|null;section_path:string|null;page_number:number|null;chunk_index?:number;retrieval_method?:string;score?:number; evidence_type?:string}
export interface SearchResult {device_id:string|null;device?:Device;matched_issues:Issue[];results:Chunk[];score_semantics?:string}
export interface Page<T> {items:T[];total:number;offset:number;limit:number}
