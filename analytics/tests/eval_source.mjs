// Offline transport only. Discovery, receipt verification and parsing are production code.
import { discoverTransfers } from '../../lib/discover.mjs';
import { ingest } from '../../lib/ingest.mjs';
import { fixture, hash, token } from '../../test/fixtures.mjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const { operation, config, selection, rejectDiscovery } = JSON.parse(input);
const f = fixture();
let result;
if (operation === 'anchor') {
  result = { endBlockHash: f.block.hash, finalizedBlock: '10', finalizedHash: f.block.hash,
    source: 'https://rpc.synthetic.example' };
} else if (operation === 'discover') {
  try {
    result = await discoverTransfers(config, { pause: async () => {}, fetchImpl: async url => {
      if (rejectDiscovery) return new Response('', { status: 402 });
      // Duplicate candidate rows across two pages must not duplicate payments.
      const second = url.searchParams.has('cursor');
      return Response.json({ data: [{ blockNumber: 10, transactionHash: hash(1), sourceToken: { address: token } }],
        nextCursor: second ? null : 'synthetic-page-2' });
    }});
  } catch (error) {
    if (error.message !== 'Discovery HTTP 402; stopped without authentication or payment') throw error;
    result = { error: { code: 'discovery_http_402' } };
  }
} else if (operation === 'ingest') {
  result = await ingest(selection, f.rpc, { synthetic: true, source: 'https://rpc.synthetic.example' });
} else throw new Error('Unexpected operation');
if (result.acquiredAt) result.acquiredAt = '2026-01-01T00:00:00Z';
process.stdout.write(JSON.stringify(result));
