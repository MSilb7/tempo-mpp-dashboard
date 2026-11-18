import test from 'node:test';
import assert from 'node:assert/strict';
import { decodeMemo, normalizeReceipt, summarize } from '../lib/tempo.mjs';
import { createRpc, ingest, validateSelection } from '../lib/ingest.mjs';
import { fixture, selection, hash, token, memo } from './fixtures.mjs';

const normalize = f => normalizeReceipt(f.receipt, { ...selection, block: f.block, synthetic: true });

test('MPP v1 exact byte boundaries and anonymous client', () => {
  assert.deepEqual(decodeMemo(memo), { status: 'mpp-v1', decoderVersion: 1, version: 1,
    serverFingerprint: '0x' + 'ab'.repeat(10), clientFingerprint: null, challengeReference: '0x' + 'cd'.repeat(7) });
  assert.equal(decodeMemo(memo.slice(0, 32) + 'ef'.repeat(10) + memo.slice(52)).clientFingerprint, '0x' + 'ef'.repeat(10));
  assert.deepEqual(decodeMemo('0x' + memo.slice(2).toUpperCase()), decodeMemo(memo));
});

test('absent, non-MPP, malformed and future memos remain distinct', () => {
  assert.equal(decodeMemo(null).status, 'absent');
  assert.equal(decodeMemo(hash(0)).status, 'non-mpp');
  for (const m of ['', memo.slice(0, -2), memo + '00', '0x' + 'zz'.repeat(32)])
    assert.equal(decodeMemo(m).status, 'malformed');
  assert.equal(decodeMemo(memo.replace('71201', '71202')).status, 'unsupported-version');
});

test('two identical payments remain two; event aliases and repeated logs count once', () => {
  const f = fixture();
  f.receipt.logs.push(structuredClone(f.receipt.logs[1]));
  f.receipt.logs.reverse();
  const rows = normalize(f);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map(t => t.evidenceLogIndexes), [['0', '1'], ['2', '3']]);
  assert.notEqual(rows[0].id, rows[1].id);
  const [total] = summarize(rows);
  assert.equal(total.grossTransferAtomic, '18014398509481986');
  assert.equal(total.unknownRoleAtomic, total.grossTransferAtomic);
  assert.equal(total.customerSpendingAtomic, null);
  assert.equal(total.downstreamProviderSpendingAtomic, null);
});

test('plain transfers, custom memos and unrelated tokens are handled without MPP claims', () => {
  const f = fixture();
  f.receipt.logs = [f.log(0), f.log(1, true), f.log(2)];
  f.receipt.logs[1].topics[3] = hash(123);
  const outside = f.log(3); outside.address = '0x20c0' + 'f'.repeat(36);
  f.receipt.logs.push(outside);
  const rows = normalize(f);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map(t => t.attribution.status), ['non-mpp', 'absent']);
});

test('ambiguous memo pairings, conflicts and malformed event payloads fail closed', () => {
  const mutations = [
    f => f.receipt.logs.shift(),
    f => { f.receipt.logs[1].data = hash(2); },
    f => { f.receipt.logs[1].logIndex = '0x9'; },
    f => { f.receipt.logs[1].address = '0x20c0' + 'f'.repeat(36); f.receipt.logs[3].logIndex = '0x8'; },
    f => { const copy = structuredClone(f.receipt.logs[0]); copy.data = hash(1); f.receipt.logs.push(copy); },
    f => { f.receipt.logs[0].data = '0x01'; },
    f => { f.receipt.logs[0].topics[1] = '0x' + 'f'.repeat(64); },
    f => { f.receipt.logs[0].topics.push(hash(0)); },
    f => { f.receipt.logs[0].removed = true; },
    f => { f.receipt.logs[0].transactionHash = hash(2); },
  ];
  for (const mutate of mutations) { const f = fixture(); mutate(f); assert.throws(() => normalize(f)); }
});

test('mint/burn and separate tokens do not inflate gross transfer or spending', () => {
  const f = fixture();
  f.receipt.logs = [f.log(0, false, 3n), f.log(1, false, 5n), f.log(2, false, 7n)];
  f.receipt.logs[0].topics[1] = hash(0);
  f.receipt.logs[1].topics[2] = hash(0);
  const rows = normalize(f);
  const totals = summarize([...rows, { ...rows[2], token: '0x20c0' + 'f'.repeat(36), amountAtomic: '11' }]);
  assert.equal(totals.length, 2);
  assert.equal(totals[0].grossTransferAtomic, '7');
  assert.equal(totals[0].mintAtomic, '3');
  assert.equal(totals[0].burnAtomic, '5');
  assert.equal(totals[0].mppV1TransferCount, 0);
  assert.equal(totals[1].grossTransferAtomic, '11');
});

test('failed receipts have zero movements; impossible failed logs are rejected', () => {
  const f = fixture(); f.receipt.status = '0x0';
  assert.throws(() => normalize(f));
  f.receipt.logs = [];
  assert.deepEqual(normalize(f), []);
});

test('selection validation bounds work before networking and normalizes duplicates', () => {
  for (const update of [{ chainId: '1' }, { tokens: [] }, { transactionHashes: [] },
    { transactionHashes: Array(101).fill(hash(1)) }, { tokens: Array(21).fill(token) },
    { tokens: ['0x' + '1'.repeat(40)] }, { transactionHashes: ['bad'] }])
    assert.throws(() => validateSelection({ ...selection, ...update }));
  assert.equal(validateSelection({ ...selection, transactionHashes: [hash(1), hash(1)] }).transactionHashes.length, 1);
});

test('bounded ingestion preserves evidence, provenance separation and honest coverage', async () => {
  const f = fixture();
  const result = await ingest({ ...selection, transactionHashes: [hash(1), hash(1)] }, f.rpc, { synthetic: true });
  assert.equal(result.coverage.requestedTransactions, 1);
  assert.equal(result.coverage.completeForSelection, true);
  assert.equal(result.coverage.completeForBlockRange, false);
  assert.equal(result.coverage.chainPopulationDenominator, null);
  assert.equal(result.coverage.unknownRoleTransfers, 2);
  assert.deepEqual(result.rawEvidence.receipts, [f.receipt]);
  assert.deepEqual(result.operatorAssertions, []);
  assert.deepEqual(result.modelInferences, []);
  assert.ok(result.transfers.every(t => t.evidence === 'synthetic' && t.paymentRole === 'unknown'));
  assert.equal(f.calls.filter(([m]) => m === 'eth_getTransactionReceipt').length, 1);
  assert.doesNotThrow(() => JSON.stringify(result));
});

test('wrong chain, missing receipts, non-finality and mismatched membership abort', async () => {
  for (const kind of ['chain', 'missing', 'pending', 'block', 'membership', 'receipt']) {
    const f = fixture();
    const rpc = async (method, params) => {
      if (kind === 'chain' && method === 'eth_chainId') return '0x1';
      if (kind === 'missing' && method === 'eth_getTransactionReceipt') return null;
      const result = await f.rpc(method, params);
      if (kind === 'pending' && params[0] === 'finalized') result.number = '0x9';
      if (kind === 'block' && method === 'eth_getTransactionReceipt') result.blockHash = hash(55);
      if (kind === 'membership' && method === 'eth_getBlockByNumber') result.transactions = [];
      if (kind === 'receipt' && method === 'eth_getTransactionReceipt') result.transactionHash = hash(5);
      return result;
    };
    await assert.rejects(ingest(selection, rpc), undefined, kind);
  }
});

test('canonical block changing during final recheck aborts entire snapshot', async () => {
  const f = fixture(); let blockReads = 0;
  await assert.rejects(ingest(selection, async (method, params) => {
    const result = await f.rpc(method, params);
    if (method === 'eth_getBlockByNumber' && ++blockReads === 3) result.hash = hash(999);
    return result;
  }), /Canonical block changed/);
});

test('RPC retries are bounded and do not leak endpoint/provider secrets', async () => {
  let calls = 0;
  const rpc = createRpc('https://rpc.example/?key=SECRET', { fetchImpl: async () => {
    calls++; throw new Error('SECRET');
  }, attempts: 2 });
  await assert.rejects(rpc('eth_chainId', []), { message: 'RPC eth_chainId failed after 2 attempts' });
  assert.equal(calls, 2);
  await assert.rejects(rpc('eth_sendRawTransaction', ['SECRET']), /not allowed/);
  assert.equal(calls, 2);
});

test('RPC validates envelopes and bounds response size', async () => {
  for (const body of [{ jsonrpc: '2.0', id: 9, result: '0x1' },
    { jsonrpc: '2.0', id: 1, error: { message: 'SECRET' } }, { data: 'x'.repeat(500) }]) {
    const rpc = createRpc('https://rpc.example', { attempts: 1, maxBytes: 100,
      fetchImpl: async () => new Response(JSON.stringify(body)) });
    await assert.rejects(rpc('eth_chainId', []), /failed after 1 attempts/);
  }
  const rpc = createRpc('https://rpc.example', { fetchImpl: async (_url, options) => {
    const req = JSON.parse(options.body);
    assert.equal(req.method, 'eth_chainId');
    return new Response(JSON.stringify({ jsonrpc: '2.0', id: req.id, result: '0x1079' }));
  } });
  assert.equal(await rpc('eth_chainId', []), '0x1079');
  assert.throws(() => createRpc('http://rpc.example'), /HTTPS/);
  assert.throws(() => createRpc('https://user:password@rpc.example'), /credentials/);
});
