# Flex transaction-review performance

Physical captures used a Ledger Flex running 1.6.1/API 26, USB, and the same
opt-in ARM32 field backport on both sides. This stack isolates the app and reply
changes; it does not include that arithmetic backport, diagnostic transport or
experimental GLV. These are historical measured deltas, not fresh measurements
of the cleaned PR commits or promises for every transaction.

The wallet prepared a two-action private send with one real input note, one
dummy spend, one recipient output and change. This is not a measurement of two
real input notes. Times sum instrumented USB spans through SDK review submission,
excluding wallet inter-command gaps, human approval and signing. Each pair used
one real transaction per build. No payloads, keys, addresses or amounts are
needed for the measurements.

| Change | Before | After | Observed saving |
|---|---:|---:|---:|
| Reuse account/viewing material and decoded input points | 10.586 s | 9.345 s | 1.241 s (11.7%) |

Initial reuse derives account/FVK/viewing material once per transaction, retains
validated external points for key agreement, and shares output diversifier work.
Each real spend still checks its own account path, randomized key, ownership,
nullifier and commitments. Viewing material is cleared before review.

Build identities for this pair are `a3c51c531d5d4e26` (control) and
`f4a513f4d35c20a0` (candidate). The unadjusted total includes transport scheduling
and diagnostic marker overhead; estimated processing saving was about 1.05 s.
Later comparisons use refreshed controls, so their deltas must not be summed
into a synthetic measurement.
