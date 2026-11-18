// Offline consistency replay through the same canonicalizer used by ingestion.
// Does not contact RPC or re-establish present-day finality.
import assert from 'node:assert/strict';
import { ingest } from '../lib/ingest.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
try {
  const s = JSON.parse(input);
  assert.equal(s.schemaVersion, 1);
  assert.ok(typeof s.synthetic === 'boolean');
  assert.ok(typeof s.acquiredAt === 'string' && Number.isFinite(Date.parse(s.acquiredAt)));
  assert.ok(typeof s.source === 'string' && s.source.length > 0);
  if (!s.synthetic) {
    const u = new URL(s.source);
    assert.equal(u.protocol, 'https:');
    assert.equal(u.origin, s.source);
  }
  assert.ok(s.rawEvidence.receipts.length > 0 && s.rawEvidence.receipts.length <= 100);
  assert.equal(new Set(s.rawEvidence.receipts.map(r => r.transactionHash)).size, s.rawEvidence.receipts.length);
  assert.equal(new Set(s.rawEvidence.blocks.map(b => b.number)).size, s.rawEvidence.blocks.length);
  const receipts = new Map(s.rawEvidence.receipts.map(r => [r.transactionHash, r]));
  const blocks = new Map(s.rawEvidence.blocks.map(b => [b.number, b]));
  const selection = { chainId: s.chainId, transactionHashes: [...receipts.keys()], tokens: s.coverage.tokenAllowlist };
  const replay = await ingest(selection, async (method, params) => {
    if (method === 'eth_chainId') return '0x' + BigInt(s.chainId).toString(16);
    if (method === 'eth_getTransactionReceipt') return receipts.get(params[0]);
    if (method === 'eth_getBlockByNumber') {
      const boundary = { number: '0x' + BigInt(s.finality.blockNumber).toString(16), hash: s.finality.blockHash };
      if (params[0] === 'finalized') return boundary;
      return blocks.get(params[0]) ?? (params[0] === boundary.number ? boundary : null);
    }
    throw new Error('Unexpected method');
  }, { synthetic: s.synthetic, source: s.source });
  assert.deepEqual(s.transfers, replay.transfers);
  assert.deepEqual(s.rawEvidence, replay.rawEvidence);
  assert.deepEqual(s.coverage, replay.coverage);
  assert.deepEqual(s.finality, replay.finality);
  assert.deepEqual(s.totals, replay.totals);
  assert.deepEqual(s.operatorAssertions, []);
  assert.deepEqual(s.modelInferences, []);
  process.stdout.write('verified-snapshot-v1\n');
} catch {
  console.error('Snapshot failed offline receipt/canonical-transfer consistency checks');
  process.exitCode = 1;
}
