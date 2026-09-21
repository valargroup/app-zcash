# Ledger I/O dependency

The app uses the published `ledger_device_sdk` 1.37.0 with `io_new` and `sys`.
No SDK fork or local SDK copy is required. `Cargo.lock` also pins published
`ledger_secure_sdk_sys` 1.16.4 and `include_gif` 1.3.2. Keep the SDK at 1.37 or
later because this release fixes command rejection and transport preservation
during NBGL review.

`io_new` sends replies without the legacy pre-reply receive wait. The app uses
its command/response API on Flex, Stax, Nano S Plus, Nano X and Apex P. The SDK
continues to service events and reject overlapping commands while a review is
pending. Zcash explicitly checks the PIN state before dispatching app commands,
preserving the locked-device refusal from legacy I/O.

Request and response storage is shared with UI event handling. Handlers retain
owned request fields before displaying a review and construct responses after
it finishes. PCZT parsing copies at most 255 payload bytes before allowing UI
callbacks to use the communication buffer. Payloads above that existing PCZT
chunk limit are refused. The SDK now checks the exact APDU framing length;
trailing bytes beyond the declared length are rejected. Both four-byte empty
APDUs and existing five-byte zero-length commands are accepted.

Emulator tests cover framing, immediate replies without new ticker events, and
approval/rejection with overlapping commands. Published Flex measurements in
[the performance report](FLEX_PERFORMANCE.md) used the earlier legacy-I/O patch.
Fresh physical-device timing and lock/reconnect checks are pending for this
migration; the old results do not establish its measured saving. Other devices
also need hardware validation. The app's `legacy_path` feature concerns its
legacy transaction protocol and is unrelated to SDK legacy I/O.
