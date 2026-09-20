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
| Retain fixed and locally derived point coordinates | 9.451 s | 8.515 s | 0.936 s (9.9%) |
| Reply directly on Flex USB | 8.515 s | 6.881 s | 1.633 s (19.2%) |

Initial reuse derives account/FVK/viewing material once per transaction, retains
validated external points for key agreement, and shares output diversifier work.
Each real spend still checks its own account path, randomized key, ownership,
nullifier and commitments. Viewing material is cleared before review.

Build identities for this pair are `a3c51c531d5d4e26` (control) and
`f4a513f4d35c20a0` (candidate). The unadjusted total includes transport scheduling
and diagnostic marker overhead; estimated processing saving was about 1.05 s.
Later comparisons use refreshed controls, so their deltas must not be summed
into a synthetic measurement.

Point reuse initializes SDK points from full coordinates already known for fixed
bases and locally derived points, and negates a point directly. External encoded
points still undergo canonical/nonidentity checks. Decodes fell 18 → 4 in the
matched capture, with estimated processing saving 0.867 s. This pair used
`f662c78888c56445` (refreshed control) and `ed6202a18e0ede42` (candidate).

The Flex USB reply patch skips the receive/tick wait immediately before replying,
while continuing to service UX events in the receive loop. The pre-reply interval
fell 1.696 → 0.042 s; full comparison is 8.514869 → 6.881416 s. Build identities
are `ed6202a18e0ede42` and `9b2707bab4b702cca`. Locked-device refusal and recovery
after USB reconnect passed on the physical candidate.

Combined key derivation returns the normalized ASK already used to build the FVK.
With recipient reuse in the next change, the refreshed pair measured
6.856293 → 6.547234 s (0.309059 s, 4.5%). Key preparation fell
0.897058 → 0.711057 s. This was a joint measurement; no isolated total-time
saving is attributed to this constructor alone. The pair used
`9b2707bab4b702cca` and `4ae16e854f12007b`.
