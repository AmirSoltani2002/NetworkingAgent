import { BadRequestException, HttpException, ServiceUnavailableException } from '@nestjs/common';
import { guardedFetch } from '../mcp/network-policy';

export interface RagTarget { restUrl: string; secret?: string; origins: string }
/** Only controller-defined operations can reach this client, never arbitrary URLs. */
export async function ragRequest(target: RagTarget, path: string, method = 'GET', body?: unknown) {
  const base = new URL(target.restUrl.endsWith('/') ? target.restUrl : target.restUrl+'/');
  const url = new URL(path.replace(/^\//,''),base);
  if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname)) throw new BadRequestException('Unsafe RAG request.');
  const headers: Record<string,string> = {};
  if (target.secret) headers.Authorization = `Bearer ${target.secret}`;
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  try {
    const response = await guardedFetch(target.restUrl,target.origins)(url,{method,headers,signal:AbortSignal.timeout(20000),body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body)});
    if (!response.ok) {
      await response.body?.cancel();
      const messages: Record<number,string> = {401:'RAG authentication failed. Check the saved token.',403:'RAG denied this operation.',404:'RAG record or endpoint was not found.',409:'RAG rejected a conflict: check duplicates, associations or processing state.',413:'Document exceeds the RAG upload limit.',422:'RAG rejected the fields. Check required fields, UUID references and metadata.',429:'RAG is busy. Try again shortly.'};
      throw new HttpException(messages[response.status] ?? 'RAG REST API failed. Check the server connection.', response.status < 500 ? response.status : 503);
    }
    if (response.status === 204) return { deleted: true };
    const result: unknown = await response.json();
    let json = JSON.stringify(result);
    if (target.secret) json = json.split(target.secret).join('[redacted]');
    return JSON.parse(json) as unknown;
  } catch (error) {
    if (error instanceof HttpException) throw error;
    throw new ServiceUnavailableException('RAG REST API is unavailable or timed out. Check the server connection.');
  }
}
