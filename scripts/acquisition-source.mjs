// JSON stdin bridge for the durable Python coordinator. No wallet or paid APIs.
import { createRpc } from '../lib/ingest.mjs';
import { acquire } from '../lib/acquisition.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
try {
  const endpoint = new URL(process.env.TEMPO_RPC_URL);
  const result = await acquire(JSON.parse(input), { rpc: createRpc(endpoint.href), source: endpoint.origin });
  process.stdout.write(JSON.stringify(result));
} catch {
  // Provider errors and environment endpoint details must not leak to logs.
  console.error('Acquisition source failed; check free-provider access, finalized bounds and per-window budgets. No payment attempted.');
  process.exitCode = 1;
}
