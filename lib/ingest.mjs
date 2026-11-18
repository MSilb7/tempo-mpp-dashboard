import { hex, quantity, normalizeReceipt, summarize } from './tempo.mjs';

export function validateSelection(selection) {
  if (!['4217', '42431'].includes(selection.chainId)) throw new Error('Expected Tempo chainId string (4217 or 42431)');
  for (const [key, max, bytes] of [['transactionHashes', 100, 32], ['tokens', 20, 20]]) {
    if (!Array.isArray(selection[key]) || !selection[key].length || selection[key].length > max)
      throw new Error(`Expected 1–${max} ${key}`);
    selection = { ...selection, [key]: [...new Set(selection[key].map(v => hex(v, bytes, key)))] };
  }
  if (selection.tokens.some(t => !t.startsWith('0x20c0'))) throw new Error('Only native TIP-20 token addresses supported');
  return selection;
}

// Only these methods can leave the process. No keys, signing or paid-job APIs.
const METHODS = new Set(['eth_chainId', 'eth_getTransactionReceipt', 'eth_getBlockByNumber']);
export function createRpc(url, { fetchImpl = fetch, timeoutMs = 10000, attempts = 3,
  maxBytes = 8 * 1024 * 1024 } = {}) {
  const endpoint = new URL(url);
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password)
    throw new Error('RPC requires HTTPS without URL user credentials');
  let id = 0;
  return async (method, params) => {
    if (!METHODS.has(method)) throw new Error('RPC method not allowed');
    const requestId = ++id;
    for (let attempt = 0; attempt < attempts; attempt++) {
      try {
        const response = await fetchImpl(endpoint, { method: 'POST', redirect: 'error',
          headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(timeoutMs),
          body: JSON.stringify({ jsonrpc: '2.0', id: requestId, method, params }) });
        if (!response.ok) { await response.body?.cancel(); throw new Error('HTTP error'); }
        const reader = response.body.getReader();
        const chunks = []; let size = 0;
        try {
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            size += value.length;
            if (size > maxBytes) throw new Error('Response limit');
            chunks.push(value);
          }
        } finally { await reader.cancel(); }
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        if (body.jsonrpc !== '2.0' || body.id !== requestId || body.error || !Object.hasOwn(body, 'result'))
          throw new Error('RPC error');
        return body.result;
      } catch {
        // Never echo provider bodies, URLs or credentials into logs.
        if (attempt === attempts - 1) throw new Error(`RPC ${method} failed after ${attempts} attempts`);
        await new Promise(resolve => setTimeout(resolve, 100 * (attempt + 1)));
      }
    }
  };
}

export async function ingest(selection, rpc, { synthetic = false, source = 'user-selected-rpc' } = {}) {
  const { chainId, transactionHashes, tokens } = validateSelection(selection);
  if (quantity(await rpc('eth_chainId', [])).toString() !== chainId) throw new Error('Wrong RPC chain');
  const finalized = await rpc('eth_getBlockByNumber', ['finalized', false]);
  if (!finalized) throw new Error('RPC finalized block unavailable');
  const finalHeight = quantity(finalized.number);
  hex(finalized.hash, 32);
  const blocks = new Map(); const receipts = []; const transfers = [];
  for (const hash of transactionHashes) {
    const receipt = await rpc('eth_getTransactionReceipt', [hash]);
    if (!receipt || hex(receipt.transactionHash, 32) !== hash) throw new Error('Missing or mismatched receipt');
    const height = quantity(receipt.blockNumber);
    if (height > finalHeight) throw new Error('Receipt is not finalized');
    const key = '0x' + height.toString(16);
    if (!blocks.has(key)) {
      const block = await rpc('eth_getBlockByNumber', [key, false]);
      if (!block || quantity(block.number) !== height) throw new Error('Missing or mismatched block');
      blocks.set(key, block);
    }
    const block = blocks.get(key);
    if (!Array.isArray(block.transactions) || !block.transactions.some(t => hex(t, 32) === hash))
      throw new Error('Transaction absent from block');
    transfers.push(...normalizeReceipt(receipt, { chainId, tokens, block, synthetic }));
    receipts.push(receipt);
  }
  // Recheck canonical hashes after acquisition; fail atomically on a reorg.
  for (const [height, block] of [...blocks, [finalized.number, finalized]]) {
    const current = await rpc('eth_getBlockByNumber', [height, false]);
    if (!current || hex(current.hash, 32) !== hex(block.hash, 32) || quantity(current.number) !== quantity(height))
      throw new Error('Canonical block changed during ingestion');
  }
  const heights = [...blocks.keys()].map(quantity);
  return {
    schemaVersion: 1, synthetic, acquiredAt: new Date().toISOString(), source,
    chainId, coverage: {
      selection: 'explicit-transaction-list', requestedTransactions: transactionHashes.length,
      acquiredTransactions: receipts.length, failedTransactions: receipts.filter(r => quantity(r.status) === 0n).length,
      tokenAllowlist: tokens, fromBlock: heights.reduce((a, b) => a < b ? a : b).toString(),
      toBlock: heights.reduce((a, b) => a > b ? a : b).toString(),
      completeForSelection: true, completeForBlockRange: false, chainPopulationDenominator: null,
      workflowCoverage: null, publicationBias: 'User-selected transactions; not a representative chain or workflow sample.',
      unknownRoleTransfers: transfers.filter(t => t.movement === 'transfer').length,
    },
    finality: { status: 'rpc-finalized', blockNumber: finalHeight.toString(), blockHash: finalized.hash,
      limitation: 'Single RPC consistency checks; no independent consensus or receipt-proof verification.' },
    transfers, totals: summarize(transfers), operatorAssertions: [], modelInferences: [],
    rawEvidence: { receipts, blocks: [...blocks.values()] },
  };
}
