# Flex transaction-review performance

## Separate measurements of the key and recipient changes

On 2026-09-21, matched Flex USB captures measured each of the three changes
separately, using three reviews per build and workload. Each build came from the
exact code commit below with the same diagnostic transport and function tracing.
All use registry `pasta_curves` 0.5.2 and Ledger randomized scalar multiplication,
without the ARM32 backport or experimental GLV. The PR code excludes profiling.

The send has two actions, one real input note plus one padding action, with a
recipient output and change. Times sum instrumented USB spans through SDK review
submission, excluding wallet inter-command gaps, human approval and signing.
They include diagnostic overhead and are not CPU time or display-refresh timing.
Retry may reuse a prepared transaction; payload identity was not recorded.
No payloads, keys, addresses or amounts are included in the measurement records.

| Change | Action order | Before → after median | Observed saving |
|---|---|---:|---:|
| Combined key derivation, `3c3903d` | Real first | 6.999 → 6.814 s | 0.185 s (2.65%) |
| Checked recipient reuse, `d65a735` | Real first | 6.814 → 6.633 s | 0.181 s (2.66%) |
| Validation-key reuse across actions, `04c8ae2` | Padding first | 6.807 → 6.600 s | 0.207 s (3.04%) |

Real-first ranges were 6.993–7.003 s before combined derivation, 6.805–6.826 s
after it, and 6.628–6.647 s after recipient reuse. The separate padding-first
comparison ranged 6.803–6.838 s before key reuse and 6.588–6.607 s after it.
Each pair matched command shape, action order and all unaffected operation counts;
all 21 completed pre-review commands per capture succeeded, with no trace errors.

Combined derivation returns the normalized authorizing key already computed for
the full viewing key. Key preparation fell 0.899 → 0.713 s and scalar calls
21 → 20 when the real input came first.

Recipient reuse carries the account-checked diversifier base and transmission key
from ownership verification into nullifier validation. Validation fell
4.961 → 4.781 s; decodes and diversifier hashes each fell 4 → 3, with scalar
calls unchanged at 20. Canonical/nonidentity checks on untrusted input remain,
and raw-recipient entry points still validate.

The final extension retains a zeroizing normalized validation scalar under the
checked account path, including when padding comes first. The later real action
reuses it while still checking its own randomized key. Key preparation fell
0.907 → 0.714 s and scalar calls 21 → 20. The scalar is wiped before review or
reset. This gain applies to the padding-first comparison; it must not be added
to the two real-first gains. A single real input processed first has no additional
scalar removal from this extension.

[Measurement data](flex-measurements-2026-09-21.json) includes exact code commits,
installed application hashes, per-run timings, medians/ranges and operation counts.
PR4/5 use their scheduled first three real-first captures; PR6 uses a separate
three-capture padding-first control. Marker-adjusted processing estimates show
reductions of approximately 186, 171 and 202 ms respectively, but remain estimates.
Each of the four profiling builds passed the same 29 transaction cases before
installation, and source projection checks verified equivalence to its PR code.

Multiple-real-input cases have emulator coverage, not new physical timings.
Matched emulator traces across both pools remove one scalar multiplication for
two real spends, or two for two real spends after a dummy. Tests use distinct
notes and randomized keys, reject a bad second key or different account after
cache reuse, and accept a fresh transaction after rejection. Key tests cover
both normalization signs and repeated alpha values. Account scope lookup order
and Ledger randomized multiplication remain unchanged.

## Earlier measurements

These earlier Flex 1.6.1/API 26 USB comparisons used the same opt-in ARM32 field
backport on both sides and one review per build. They explain the earlier fixes,
but are not timings of the cleaned code commits in the new configuration.
Do not combine their absolute timings with the separate measurements above.

| Change | Before | After | Observed saving |
|---|---:|---:|---:|
| Reuse account/viewing material and decoded input points | 10.586 s | 9.345 s | 1.241 s (11.7%) |
| Retain fixed and locally derived point coordinates | 9.451 s | 8.515 s | 0.936 s (9.9%) |
| Earlier legacy-I/O USB reply patch | 8.515 s | 6.881 s | 1.633 s (19.2%) |
| Combined key derivation + recipient reuse (joint capture) | 6.856 s | 6.547 s | 0.309 s (4.5%) |

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

The reply change now uses the published SDK's `io_new` API instead of an SDK
fork. This migration has not been retimed on a physical Flex. The row above
records the earlier implementation; it is not a measurement of the new path.

The earlier joint key/recipient pair used `9b2707bab4b702cca` and
`4ae16e854f12007b`. Key preparation fell 0.897058 → 0.711057 s and validation
4.825009 → 4.688975 s. Its 0.309059 s total saving belonged to both changes
combined; the new separate captures above now isolate their individual effects.
