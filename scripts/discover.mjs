import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { discoverTransfers } from '../lib/discover.mjs';

const [input, output, ...extra] = process.argv.slice(2);
if (!input || !output || extra.length) {
  console.error('Usage: node scripts/discover.mjs .local/window.json .local/discovery.json');
  process.exitCode = 1;
} else {
  try {
    const result = await discoverTransfers(JSON.parse(await readFile(input, 'utf8')));
    await mkdir(dirname(resolve(output)), { recursive: true });
    await writeFile(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
    console.log(`Discovered ${result.selection.transactionHashes.length} candidate transactions; receipt verification required.`);
  } catch (error) {
    console.error(error.message); process.exitCode = 1;
  }
}
