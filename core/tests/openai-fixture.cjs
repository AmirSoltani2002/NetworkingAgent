// Existing short-chat fixtures are well below the compaction threshold.
exports.withTokenCount = handler => (url, options) => String(url).endsWith('/input_tokens')
  ? Promise.resolve(new Response(JSON.stringify({object:'response.input_tokens',input_tokens:100})))
  : handler(url, options);
