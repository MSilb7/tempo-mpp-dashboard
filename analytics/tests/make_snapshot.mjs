// Invented receipts only; exercise the real ingestion serializer without RPC.
import { ingest } from '../../lib/ingest.mjs';
import { fixture, hash, token, memo } from '../../test/fixtures.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const options = JSON.parse(input);
const universe = options.universe ?? [{ id: 1, day: 1 }, { id: 2, day: 2 }, { id: 3, day: 3 }];
const blocks = new Map(); const receipts = new Map();
for (const spec of universe) {
  const number = '0x' + (1000 + spec.day).toString(16);
  const blockHash = hash(1000 + spec.day + (options.reorg ? 10000 : 0));
  if (!blocks.has(number)) blocks.set(number, { number, hash: blockHash,
    timestamp: '0x' + (Date.UTC(2026, 0, spec.day) / 1000).toString(16), transactions: [] });
  blocks.get(number).transactions.push(hash(spec.id));
  const f = fixture();
  const logs = [f.log(0, false, BigInt(spec.amount ?? spec.id * 100)),
    f.log(1, true, BigInt(spec.amount ?? spec.id * 100))];
  for (const log of logs) Object.assign(log, { transactionHash: hash(spec.id), blockNumber: number, blockHash });
  if (spec.memo === 'absent') logs.splice(1);
  else if (spec.memo === 'other') logs[1].topics[3] = hash(12);
  else if (spec.client) logs[1].topics[3] = memo.slice(0, 32) + 'ef'.repeat(10) + memo.slice(52);
  if (spec.movement === 'mint') for (const log of logs) log.topics[1] = hash(0);
  if (spec.failed) logs.length = 0;
  receipts.set(hash(spec.id), { transactionHash: hash(spec.id), blockNumber: number, blockHash,
    status: spec.failed ? '0x0' : '0x1', logs });
}
const final = [...blocks.values()].sort((a,b) => Number(BigInt(a.number)-BigInt(b.number))).at(-1);
const result = await ingest({ chainId: '4217', transactionHashes: options.ids.map(hash), tokens: [token] }, async (method, params) => {
  if (method === 'eth_chainId') return '0x1079';
  if (method === 'eth_getTransactionReceipt') return receipts.get(params[0]);
  if (method === 'eth_getBlockByNumber') return params[0] === 'finalized' ? final : blocks.get(params[0]);
  throw new Error('Unexpected method');
}, { synthetic: options.synthetic ?? true, source: 'https://rpc.synthetic.example' });
result.acquiredAt = options.acquiredAt ?? '2026-02-01T00:00:00Z';
process.stdout.write(JSON.stringify(result));
