// ABI and memo sources, assumptions and upgrade boundaries: docs/EVIDENCE.md.
export const TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';
export const TRANSFER_WITH_MEMO = '0x57bc7354aa85aed339e000bccffabbc529466af35f0772c8f8ee1145927de7f0';
export const MPP_TAG = 'ef1ed712'; // keccak256("mpp")[0:4]
const ZERO = '0x' + '0'.repeat(40);

export function hex(value, bytes, label = 'hex') {
  if (typeof value !== 'string' || !new RegExp(`^0x[0-9a-fA-F]{${bytes * 2}}$`).test(value))
    throw new Error(`Invalid ${label}`);
  return value.toLowerCase();
}

export function quantity(value) {
  if (typeof value !== 'string' || !/^0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)$/.test(value))
    throw new Error('Invalid RPC quantity');
  return BigInt(value);
}

export function decodeMemo(memo) {
  if (memo === null) return { status: 'absent', decoderVersion: 1 };
  if (typeof memo !== 'string' || !/^0x[0-9a-fA-F]{64}$/.test(memo))
    return { status: 'malformed', decoderVersion: 1 };
  const raw = memo.slice(2).toLowerCase();
  if (!raw.startsWith(MPP_TAG)) return { status: 'non-mpp', decoderVersion: 1 };
  const version = parseInt(raw.slice(8, 10), 16);
  if (version !== 1) return { status: 'unsupported-version', version, decoderVersion: 1 };
  const client = raw.slice(30, 50);
  return {
    status: 'mpp-v1', decoderVersion: 1, version,
    serverFingerprint: '0x' + raw.slice(10, 30),
    clientFingerprint: /^0+$/.test(client) ? null : '0x' + client,
    challengeReference: '0x' + raw.slice(50),
  };
}

function addressTopic(topic) {
  const word = hex(topic, 32, 'address topic');
  if (!word.startsWith('0x' + '0'.repeat(24))) throw new Error('Noncanonical address topic');
  return '0x' + word.slice(26);
}

// Full receipts are required: adjacency is checked against global log indexes.
// Never match by amount alone or collapse repeated same-value transfers.
export function normalizeReceipt(receipt, { chainId, tokens, block, synthetic = false }) {
  const transactionHash = hex(receipt.transactionHash, 32, 'transaction hash');
  const blockHash = hex(receipt.blockHash, 32, 'block hash');
  const blockNumber = quantity(receipt.blockNumber).toString();
  if (blockHash !== hex(block.hash, 32) || blockNumber !== quantity(block.number).toString())
    throw new Error('Receipt/block mismatch');
  const status = quantity(receipt.status);
  if (![0n, 1n].includes(status) || !Array.isArray(receipt.logs)) throw new Error('Invalid receipt');
  if (status === 0n && receipt.logs.length) throw new Error('Failed receipt contains logs');
  const allowed = new Set(tokens.map(t => hex(t, 20)));
  const logs = new Map();
  for (const log of receipt.logs) {
    const index = quantity(log.logIndex).toString();
    if (log.removed === true) throw new Error('Removed log');
    if (hex(log.transactionHash, 32) !== transactionHash || hex(log.blockHash, 32) !== blockHash ||
        quantity(log.blockNumber).toString() !== blockNumber) throw new Error('Log/receipt mismatch');
    const canonical = { address: hex(log.address, 20), topics: log.topics.map(t => hex(t, 32)),
      data: log.data, logIndex: index };
    if (logs.has(index) && JSON.stringify(logs.get(index)) !== JSON.stringify(canonical))
      throw new Error('Conflicting duplicate log index');
    logs.set(index, canonical);
  }
  const transfers = [];
  for (const log of [...logs.values()].sort((a, b) => BigInt(a.logIndex) < BigInt(b.logIndex) ? -1 : 1)) {
    if (!allowed.has(log.address)) continue;
    const topic = log.topics[0];
    if (topic !== TRANSFER && topic !== TRANSFER_WITH_MEMO) continue;
    if (log.topics.length !== (topic === TRANSFER ? 3 : 4)) throw new Error('Invalid transfer topic count');
    const payer = addressTopic(log.topics[1]);
    const recipient = addressTopic(log.topics[2]);
    const amountAtomic = BigInt(hex(log.data, 32, 'amount word')).toString();
    if (topic === TRANSFER_WITH_MEMO) {
      const previous = transfers.at(-1);
      if (!previous || previous.memo !== null || BigInt(previous.logIndex) + 1n !== BigInt(log.logIndex) ||
          previous.token !== log.address || previous.payer !== payer || previous.recipient !== recipient ||
          previous.amountAtomic !== amountAtomic)
        throw new Error('Unpaired TransferWithMemo; refusing ambiguous accounting');
      previous.memo = log.topics[3];
      previous.attribution = decodeMemo(previous.memo);
      previous.evidenceLogIndexes.push(log.logIndex);
      continue;
    }
    transfers.push({
      id: `${chainId}:${transactionHash}:${log.logIndex}`, chainId, transactionHash,
      blockHash, blockNumber, timestamp: quantity(block.timestamp).toString(),
      logIndex: log.logIndex, evidenceLogIndexes: [log.logIndex], token: log.address,
      payer, recipient, amountAtomic, decimals: null, memo: null, attribution: decodeMemo(null),
      movement: payer === ZERO ? 'mint' : recipient === ZERO ? 'burn' : 'transfer',
      evidence: synthetic ? 'synthetic' : 'chain-verified',
      verificationMethod: synthetic ? 'fixture' : 'rpc-receipt-and-block-consistency',
      finalityStatus: 'rpc-finalized', paymentRole: 'unknown',
    });
  }
  return transfers;
}

export function summarize(transfers) {
  const totals = new Map();
  for (const t of transfers) {
    const key = `${t.chainId}:${t.token}`;
    if (!totals.has(key)) totals.set(key, { chainId: t.chainId, token: t.token,
      grossTransferAtomic: 0n, mintAtomic: 0n, burnAtomic: 0n,
      unknownRoleAtomic: 0n, transferCount: 0, mppV1TransferCount: 0,
      customerSpendingAtomic: null, downstreamProviderSpendingAtomic: null });
    const total = totals.get(key);
    const amount = BigInt(t.amountAtomic);
    if (t.movement === 'transfer') {
      total.grossTransferAtomic += amount;
      total.unknownRoleAtomic += amount;
      total.transferCount++;
      if (t.attribution.status === 'mpp-v1') total.mppV1TransferCount++;
    } else total[t.movement === 'mint' ? 'mintAtomic' : 'burnAtomic'] += amount;
  }
  return [...totals.values()].map(t => Object.fromEntries(Object.entries(t).map(([k, v]) =>
    [k, typeof v === 'bigint' ? v.toString() : v])));
}
