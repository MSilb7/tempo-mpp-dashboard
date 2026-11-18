import { hex } from './tempo.mjs';

// REST discovers candidate hashes. Receipt verification, memo decoding and
// accounting remain in ingest.mjs; API labels never become chain facts here.
export async function discoverTransfers({ chainId, fromBlock, toBlock, tokens, maxPages = 10 },
  { fetchImpl = fetch, pause = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  if (!['4217', '42431'].includes(chainId)) throw new Error('Expected Tempo chain ID');
  if (![fromBlock, toBlock].every(n => Number.isSafeInteger(n) && n >= 0) ||
      toBlock < fromBlock || toBlock - fromBlock >= 1000) throw new Error('Select at most 1000 explicit blocks');
  if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > 20) throw new Error('Expected 1–20 pages');
  if (!Array.isArray(tokens) || tokens.length < 1 || tokens.length > 20) throw new Error('Expected 1–20 tokens');
  tokens = [...new Set(tokens.map(t => hex(t, 20)))];
  if (tokens.some(t => !t.startsWith('0x20c0'))) throw new Error('Expected native TIP-20 tokens');
  const hashes = new Set(); const cursors = new Set();
  let cursor = null; let pages = 0; let apiRows = 0;
  do {
    if (pages >= maxPages) throw new Error('Discovery page budget exhausted; narrow the block window');
    if (pages) await pause(3100); // below documented anonymous default; shared quota may still exhaust
    const url = new URL('https://api.tempo.xyz/v1/transfers');
    for (const [key, value] of Object.entries({ chainId, 'blockNumber.from': fromBlock,
      'blockNumber.to': toBlock, order: 'asc', limit: 50 })) url.searchParams.set(key, String(value));
    if (cursor) url.searchParams.set('cursor', cursor);
    let response;
    try { response = await fetchImpl(url, { redirect: 'error', signal: AbortSignal.timeout(10000) }); }
    catch { throw new Error('Discovery network request failed'); }
    if (!response.ok) {
      await response.body?.cancel();
      throw new Error(`Discovery HTTP ${response.status}; stopped without authentication or payment`);
    }
    const reader = response.body.getReader(); const chunks = []; let bytes = 0;
    try {
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        bytes += value.length;
        if (bytes > 2 * 1024 * 1024) throw new Error('Discovery response too large');
        chunks.push(value);
      }
    } finally { await reader.cancel(); }
    let body;
    try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
    catch { throw new Error('Invalid discovery JSON'); }
    if (!Array.isArray(body.data) || body.data.length > 50 ||
        !(body.nextCursor === null || (typeof body.nextCursor === 'string' && body.nextCursor.length > 0)))
      throw new Error('Invalid discovery page');
    for (const row of body.data) {
      if (!Number.isSafeInteger(row.blockNumber) || row.blockNumber < fromBlock || row.blockNumber > toBlock)
        throw new Error('Discovery row outside requested window');
      const hash = hex(row.transactionHash, 32);
      const token = hex(row.sourceToken?.address, 20);
      if (tokens.includes(token)) hashes.add(hash);
      if (hashes.size > 100) throw new Error('Receipt budget exceeded; narrow the block window');
    }
    pages++; apiRows += body.data.length;
    cursor = body.nextCursor;
    if (cursor && cursors.has(cursor)) throw new Error('Repeated discovery cursor');
    if (cursor) cursors.add(cursor);
  } while (cursor);
  return { schemaVersion: 1, acquiredAt: new Date().toISOString(),
    selection: { chainId, tokens, transactionHashes: [...hashes].sort() },
    discovery: { source: 'https://api.tempo.xyz/v1/transfers', fromBlock, toBlock,
      pages, apiRows, paginationExhausted: true, chainCompletenessVerified: false,
      limitation: 'Candidate discovery only. Indexer lag or missing history is not ruled out; verify receipts and coverage separately.' } };
}
