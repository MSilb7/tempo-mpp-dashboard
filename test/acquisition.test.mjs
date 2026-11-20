import test from 'node:test';
import assert from 'node:assert/strict';
import { acquire } from '../lib/acquisition.mjs';
import { fixture, selection, token, hash } from './fixtures.mjs';

test('checkpoint anchor requires the expected chain and finalized range end', async () => {
  const f = fixture();
  const config = { chainId: '4217', toBlock: 10 };
  const anchor = await acquire({ operation: 'anchor', config }, { rpc:f.rpc, source:'https://rpc.example' });
  assert.equal(anchor.endBlockHash, f.block.hash);
  await assert.rejects(acquire({ operation:'anchor', config:{...config,chainId:'42431'} }, {rpc:f.rpc}), /Wrong chain/);
  await assert.rejects(acquire({ operation:'anchor', config:{...config,toBlock:11} }, {rpc:f.rpc}), /not finalized/);
  await assert.rejects(acquire({ operation:'anchor', config }, {rpc:async (method, params) => {
    if (method==='eth_chainId') return '0x1079';
    return {...f.block, hash:params[0]==='finalized'?hash(999):f.block.hash};
  }}), /Inconsistent/);
});
test('checkpoint adapter preserves bounded discovery and receipt verification', async () => {
  const result=await acquire({operation:'discover',config:{chainId:'4217',fromBlock:10,toBlock:10,tokens:[token]}},
    {fetchImpl:async()=>new Response(JSON.stringify({data:[{blockNumber:10,transactionHash:hash(1),sourceToken:{address:token}}],nextCursor:null}))});
  assert.deepEqual(result.selection, selection);
  const snapshot=await acquire({operation:'ingest',selection:result.selection}, {rpc:fixture().rpc,source:'https://rpc.example'});
  assert.equal(snapshot.transfers.length,2);
  assert.equal(snapshot.coverage.completeForBlockRange,false);
  await assert.rejects(acquire({operation:'pay'}, {}), /Unsupported/);
});
