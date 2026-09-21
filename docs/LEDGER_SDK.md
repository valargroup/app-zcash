# Flex USB reply dependency

The app enables `fast_usb_reply` on its `ledger_device_sdk` 1.37 dependency.
The root `[patch.crates-io]` pins `ledger_device_sdk`, `ledger_secure_sdk_sys`
and `include_gif` to `f076221a7cbb8fb1efdacd68749a993c1b794b01` in the Valar SDK fork.
Keep these three revisions together when updating the dependency. The separate
key-test workspace, when present, needs its own patch table and lockfile.

The fork changes the legacy reply condition only for Flex USB HID. Receive-loop
UX handling and the in-progress command guard remain active. The SDK feature is
disabled by default; this app opts in. The SDK source is fetched by Cargo and is
not part of the app's vendored dependency refresh scripts.

The fork starts from the same source tree as published SDK 1.37.0
(`8057ecc256cf6fa2af5254031cd9fa95671e5f5e`), and its I/O source matches the
previously measured app-local patch. Physical tests of that patch reduced the
pre-reply interval from 1.696 to 0.042 s and passed lock/reconnect recovery.
Emulator tests cover overlapping command rejection and pending review responses.
See [the performance report](FLEX_PERFORMANCE.md) for measurement scope; this
dependency relocation does not introduce a new physical timing claim.
