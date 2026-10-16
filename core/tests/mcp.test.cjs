require('reflect-metadata');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const { randomBytes } = require('node:crypto');
const { McpServer } = require('@modelcontextprotocol/sdk/server/mcp.js');
const { StreamableHTTPServerTransport } = require('@modelcontextprotocol/sdk/server/streamableHttp.js');
const { McpService, validateMcpConfiguration } = require('../dist/mcp/mcp.service.js');

test('MCP URLs and credential references are validated', () => {
  assert.equal(validateMcpConfiguration({ name: ' Retrieval ', url: 'http://rag-api:8090/mcp', authEnvVar: 'RAG_API_KEY' }).name, 'Retrieval');
  for (const url of ['file:///tmp/server', 'http://user:password@host/mcp', 'http://host/mcp?token=secret', 'http://host/mcp#secret', 'not a URL']) {
    assert.throws(() => validateMcpConfiguration({ name: 'Server', url }));
  }
  assert.throws(() => validateMcpConfiguration({ name: 'Server', url: 'http://host/mcp', authEnvVar: 'raw-secret-value' }));
  assert.throws(() => validateMcpConfiguration({ name: 'Server', url: 'http://host/mcp', password: 'secret' }));
});

test('official MCP discovery, explicit allowlisting, secret-safe failures and no execution', async () => {
  const secret = randomBytes(32).toString('hex');
  let calls = 0;
  const server = createServer(async (req, res) => {
    if (req.headers.authorization !== `Bearer ${secret}`) { res.writeHead(401); res.end(); return; }
    if (req.method !== 'POST') { res.writeHead(405); res.end(); return; }
    const mcp = new McpServer({ name: 'fixture', version: '1' });
    mcp.registerTool('retrieve', { description: `Retrieval ${secret}`, inputSchema: {}, annotations: { readOnlyHint: true } }, async () => { calls++; return { content: [] }; });
    mcp.registerTool('write_data', { inputSchema: {}, annotations: { readOnlyHint: false } }, async () => { calls++; return { content: [] }; });
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    res.on('close', () => { void transport.close(); void mcp.close(); });
    await mcp.connect(transport); await transport.handleRequest(req, res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const row = { id: 'a', name: 'fixture', url: `http://127.0.0.1:${server.address().port}/mcp`, auth_env_var: 'MCP_FIXTURE_TOKEN', tools: [], allowed_tools: [], status: 'unconnected' };
  const db = { pool: { query: async (sql, params) => {
    if (sql.includes('SET tools=')) { row.tools = JSON.parse(params[1]); row.allowed_tools = params[2]; row.status = 'connected'; }
    else if (sql.includes("status='failed'")) { row.status = 'failed'; row.last_error = params[1]; }
    else if (sql.includes('SET allowed_tools=')) row.allowed_tools = params[1];
    return { rows: [row] };
  } } };
  let credential = secret;
  const service = new McpService(db, { read: async () => ({ MCP_FIXTURE_TOKEN: credential, RAG_ALLOWED_ORIGINS: new URL(row.url).origin }) });
  try {
    const result = await service.discover('a');
    assert.equal(result.status, 'connected'); assert.equal(result.tools.length, 2); assert.equal(calls, 0);
    assert(!JSON.stringify(result).includes(secret)); assert.deepEqual(result.allowedTools, []);
    await assert.rejects(service.allow('a', { allowedTools: ['write_data'] }));
    await assert.rejects(service.allow('a', { allowedTools: ['missing'] }));
    assert.deepEqual((await service.allow('a', { allowedTools: ['retrieve'] })).allowedTools, ['retrieve']);
    credential = undefined;
    await assert.rejects(service.discover('a'), /missing from the root .env/);
    credential = 'wrong-credential';
    await assert.rejects(service.discover('a'), /MCP discovery failed/);
    assert(!row.last_error.includes(secret)); assert.equal(calls, 0);
    credential=secret;row.status='connected';row.rag_enabled=true;row.agent_enabled=true;
    await service.execute('a','retrieve',{});assert.equal(calls,1);
    row.allowed_tools=[];await assert.rejects(service.execute('a','retrieve',{}),/not permitted/);assert.equal(calls,1);
    row.allowed_tools=['write_data'];await assert.rejects(service.execute('a','write_data',{}),/confirmation is required/);
  } finally { await new Promise(resolve => server.close(resolve)); }
});
