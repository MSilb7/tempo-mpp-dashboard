import test from 'node:test';
import assert from 'node:assert/strict';
import { discoverTransfers } from '../lib/discover.mjs';
import { hash, token } from './fixtures.mjs';
const config = { chainId: '4217', fromBlock: 10, toBlock: 11, tokens: [token] };
const row = (id = 1) => ({ blockNumber: 10, transactionHash: hash(id), sourceToken: { address: token },
  attribution: 'untrusted service label' });
const page = (data, nextCursor = null) => new Response(JSON.stringify({ data, nextCursor }));
test('cursor traversal uses frozen bounds, deduplicates hashes and ignores attribution labels', async () => {
  let calls = 0;
  const result = await discoverTransfers(config, { pause: async () => {}, fetchImpl: async url => {
    assert.equal(url.searchParams.get('blockNumber.to'), '11');
    assert.equal(url.searchParams.get('order'), 'asc');
    if (++calls === 1) return page([row(), row()], 'next');
    assert.equal(url.searchParams.get('cursor'), 'next');
    return page([row(), row(2)]);
  } });
  assert.deepEqual(result.selection.transactionHashes, [hash(1), hash(2)]);
  assert.equal(result.discovery.chainCompletenessVerified, false);
  assert.ok(!JSON.stringify(result).includes('untrusted service label'));
});
test('payment/auth/quota errors stop immediately without retries or credentials', async () => {
  for (const status of [401, 402, 429, 500]) {
    let calls = 0;
    await assert.rejects(discoverTransfers(config, { fetchImpl: async (_url, options) => {
      calls++; assert.equal(options.headers, undefined); return new Response('', { status });
    } }), new RegExp(`HTTP ${status}`));
    assert.equal(calls, 1);
  }
});
test('budget exhaustion, repeating cursors and out-of-range rows fail without a partial result', async () => {
  await assert.rejects(discoverTransfers({ ...config, maxPages: 1 }, {
    fetchImpl: async () => page([row()], 'next') }), /budget/);
  await assert.rejects(discoverTransfers(config, { pause: async () => {},
    fetchImpl: async () => page([row()], 'same') }), /Repeated/);
  await assert.rejects(discoverTransfers(config, {
    fetchImpl: async () => page([{ ...row(), blockNumber: 12 }]) }), /outside/);
  await assert.rejects(discoverTransfers({ ...config, toBlock: 2000 }), /1000/);
});
test('empty windows are explicit and token selection excludes unrelated rows', async () => {
  const result = await discoverTransfers(config, { fetchImpl: async () => page([
    { ...row(), sourceToken: { address: '0x20c0' + 'f'.repeat(36) } }]) });
  assert.deepEqual(result.selection.transactionHashes, []);
  assert.equal(result.discovery.paginationExhausted, true);
});
