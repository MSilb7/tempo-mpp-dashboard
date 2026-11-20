import { discoverTransfers } from './discover.mjs';
import { ingest } from './ingest.mjs';
import { hex, quantity } from './tempo.mjs';

// Shared read-only adapter used by the durable coordinator's JSON bridge.
export async function acquire({ operation, config, selection }, { rpc, source, fetchImpl }) {
  if (operation === 'anchor') {
    if (quantity(await rpc('eth_chainId', [])).toString() !== config.chainId) throw new Error('Wrong chain');
    const boundary = await rpc('eth_getBlockByNumber', ['finalized', false]);
    const end = await rpc('eth_getBlockByNumber', ['0x' + BigInt(config.toBlock).toString(16), false]);
    if (quantity(boundary.number) < BigInt(config.toBlock) || quantity(end.number) !== BigInt(config.toBlock))
      throw new Error('Range is not finalized');
    if (quantity(boundary.number) === quantity(end.number) && hex(boundary.hash,32) !== hex(end.hash,32))
      throw new Error('Inconsistent finalized boundary');
    return { endBlockHash: hex(end.hash, 32), finalizedBlock: quantity(boundary.number).toString(),
      finalizedHash: hex(boundary.hash, 32), source };
  }
  if (operation === 'discover') return discoverTransfers(config, { fetchImpl });
  if (operation === 'ingest') return ingest(selection, rpc, { source });
  throw new Error('Unsupported operation');
}
