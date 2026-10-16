import { BadRequestException } from '@nestjs/common';
import { BlockList, isIP } from 'node:net';
import { lookup } from 'node:dns';
import { request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';

export const localRagOrigins = 'http://rag-api:8090,http://rag:8090,http://localhost:8090,http://127.0.0.1:8090';
export const localMcpOrigins = localRagOrigins + ',http://manufacturing-ml:8000,http://localhost:8100,http://127.0.0.1:8100';
export const mcpOrigins = (values: Record<string,string|undefined>) => values.MCP_ALLOWED_ORIGINS ?? (values.RAG_ALLOWED_ORIGINS ? values.RAG_ALLOWED_ORIGINS + ',http://manufacturing-ml:8000,http://localhost:8100,http://127.0.0.1:8100' : localMcpOrigins);
const blocked = new BlockList();
for (const [address, prefix] of [['0.0.0.0',8],['169.254.0.0',16],['224.0.0.0',4],['240.0.0.0',4],['100.64.0.0',10],['198.18.0.0',15]] as const) blocked.addSubnet(address,prefix,'ipv4');
for (const [address,prefix] of [['::',128],['fe80::',10],['ff00::',8],['::ffff:169.254.0.0',112]] as const) blocked.addSubnet(address,prefix,'ipv6');
blocked.addAddress('fd00:ec2::254','ipv6');
export function safeAddress(address: string) {
  const mapped = address.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/i);
  if (mapped) return safeAddress(mapped[1]);
  const family = isIP(address);
  return family !== 0 && !blocked.check(address, family === 4 ? 'ipv4' : 'ipv6');
}
export function approvedUrl(raw: string, origins: string = process.env.RAG_ALLOWED_ORIGINS ?? localRagOrigins) {
  let url: URL;
  try { url = new URL(raw); } catch { throw new BadRequestException('Use an absolute HTTP or HTTPS URL.'); }
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.hash || url.search || raw.length > 2048) throw new BadRequestException('URL must use HTTP(S) without credentials, query parameters or fragments.');
  if (!origins.split(',').map(value => value.trim()).includes(url.origin)) throw new BadRequestException('Server origin is not approved. Add its exact HTTP(S) origin to MCP_ALLOWED_ORIGINS (MCP) or RAG_ALLOWED_ORIGINS (REST) in the root .env.');
  const host = url.hostname.replace(/^\[|\]$/g,'');
  if (isIP(host) && !safeAddress(host)) throw new BadRequestException('This server address is unsafe.');
  return url;
}
/** Resolve and validate on the actual socket lookup, preventing DNS rebinding. */
export function guardedFetch(endpoint: string, origins: string): typeof fetch {
  const approved = approvedUrl(endpoint, origins);
  return async (input, init) => {
    const req = new Request(input, init);
    const url = new URL(req.url);
    if (url.origin !== approved.origin || url.username || url.password) throw new Error('Cross-origin MCP request rejected');
    const data = req.body ? Buffer.from(await req.arrayBuffer()) : undefined;
    if (req.signal.aborted) throw new Error('Request aborted');
    return new Promise<Response>((resolve, reject) => {
      const native = (url.protocol === 'https:' ? httpsRequest : httpRequest)(url, {
        method: req.method, headers: Object.fromEntries(req.headers), signal: req.signal,
        lookup: (hostname, options, callback) => {
          lookup(hostname, { all: true, verbatim: true }, (error, addresses) => {
            if (error || !addresses.length || addresses.some(item => !safeAddress(item.address))) { callback(new Error('Unsafe or unresolved server address'),'',4); return; }
            if (options.all) (callback as unknown as (error: null, items: {address:string;family:number}[]) => void)(null,addresses);
            else callback(null,addresses[0].address,addresses[0].family);
          });
        },
      }, response => {
        const status = response.statusCode ?? 500;
        if (status >= 300 && status < 400) { response.destroy(); reject(new Error('Server redirects are not permitted')); return; }
        const headers = new Headers();
        for (const [key,value] of Object.entries(response.headers)) if (value !== undefined) headers.set(key,Array.isArray(value) ? value.join(', ') : value);
        let size = 0;
        const stream = new ReadableStream<Uint8Array>({
          async start(controller) {
            try {
              for await (const chunk of response) {
                size += chunk.length;
                if (size > 4 * 1024 * 1024) throw new Error('Remote response exceeds limit');
                controller.enqueue(chunk);
              }
              controller.close();
            } catch { response.destroy(); controller.error(new Error('Remote response failed or exceeds limit')); }
          }, cancel() { response.destroy(); },
        });
        if ([204,205,304].includes(status)) { response.resume(); resolve(new Response(null,{status,headers})); }
        else resolve(new Response(stream,{status,headers}));
      });
      native.on('error', () => reject(new Error('Server connection failed')));
      native.end(data);
    });
  };
}
