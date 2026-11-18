// Entirely synthetic identifiers and values. No real transaction/job records.
import { TRANSFER, TRANSFER_WITH_MEMO } from '../lib/tempo.mjs';
export const hash = n => '0x' + n.toString(16).padStart(64, '0');
export const token = '0x20c0' + '0'.repeat(35) + '1';
export const payer = '0x' + '1'.repeat(40);
export const recipient = '0x' + '2'.repeat(40);
export const memo = '0xef1ed71201' + 'ab'.repeat(10) + '00'.repeat(10) + 'cd'.repeat(7);
export const selection = { chainId: '4217', tokens: [token], transactionHashes: [hash(1)] };
export function fixture() {
  const block = { number: '0xa', hash: hash(10), timestamp: '0x6553f100', transactions: [hash(1)] };
  const log = (index, withMemo = false, amount = 9007199254740993n) => ({
    address: token, blockHash: block.hash, blockNumber: block.number, transactionHash: hash(1),
    logIndex: '0x' + index.toString(16), removed: false,
    topics: [withMemo ? TRANSFER_WITH_MEMO : TRANSFER, '0x' + '0'.repeat(24) + payer.slice(2),
      '0x' + '0'.repeat(24) + recipient.slice(2), ...(withMemo ? [memo] : [])],
    data: hash(amount),
  });
  const receipt = { transactionHash: hash(1), blockHash: block.hash, blockNumber: block.number,
    status: '0x1', logs: [log(0), log(1, true), log(2), log(3, true)] };
  const calls = [];
  const rpc = async (method, params) => {
    calls.push([method, params]);
    if (method === 'eth_chainId') return '0x1079';
    if (method === 'eth_getTransactionReceipt') return structuredClone(receipt);
    if (method === 'eth_getBlockByNumber') return structuredClone(block);
    throw new Error('Unexpected method');
  };
  return { block, receipt, log, rpc, calls };
}
