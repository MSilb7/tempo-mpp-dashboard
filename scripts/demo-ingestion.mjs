import { mkdir, writeFile } from 'node:fs/promises';
import { ingest } from '../lib/ingest.mjs';
import { fixture, selection } from '../test/fixtures.mjs';

const result = await ingest(selection, fixture().rpc, { synthetic: true, source: 'synthetic-offline-fixture' });
await mkdir('.local', { recursive: true });
await writeFile('.local/synthetic-ingestion.json', JSON.stringify(result, null, 2) + '\n');
console.log('Saved synthetic offline ingestion to .local/synthetic-ingestion.json');
