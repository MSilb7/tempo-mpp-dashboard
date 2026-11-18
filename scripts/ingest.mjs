import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { createRpc, ingest } from '../lib/ingest.mjs';

const [selectionPath, outputPath, ...extra] = process.argv.slice(2);
if (!selectionPath || !outputPath || extra.length || !process.env.TEMPO_RPC_URL) {
  console.error('Usage: TEMPO_RPC_URL=https://PUBLIC_RPC node scripts/ingest.mjs selection.json .local/sample.json');
  process.exitCode = 1;
} else {
  try {
    const input = JSON.parse(await readFile(selectionPath, 'utf8'));
    const selection = input.selection ?? input;
    const rpc = createRpc(process.env.TEMPO_RPC_URL);
    const result = await ingest(selection, rpc, { source: new URL(process.env.TEMPO_RPC_URL).origin });
    const target = resolve(outputPath);
    await mkdir(dirname(target), { recursive: true });
    // Exclusive creation prevents overwriting an earlier evidence snapshot.
    await writeFile(target, JSON.stringify(result, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    console.log(`Saved ${result.transfers.length} canonical movements from ${result.coverage.acquiredTransactions} receipts.`);
  } catch (error) {
    // Input/output OS errors may contain paths; RPC errors are sanitized in createRpc.
    console.error(`Ingestion failed: ${error.message}`);
    process.exitCode = 1;
  }
}
