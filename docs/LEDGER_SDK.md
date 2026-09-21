# USB reply dependency

The app enables `fast_usb_reply` on its `ledger_device_sdk` 1.37 dependency.
The root `[patch.crates-io]` pins `ledger_device_sdk`, `ledger_secure_sdk_sys`
and `include_gif` to `4dfcb1fa29e8e5ef017dbb688935beecc6699200` in the Valar SDK fork.
Keep these three revisions together when updating the dependency. The separate
key-test workspace, when present, needs its own patch table and lockfile.

The fork skips the legacy pre-reply receive for USB HID on Flex, Stax and
Nano S Plus. Nano S Plus has this wait only with `nano_nbgl`, which this app
enables by default. Receive-loop UX handling and the in-progress command guard
remain active. The SDK feature is disabled by default; this app opts in.
Other devices, transports and `io_new` retain their behavior. Cargo fetches the
SDK source separately from the app's vendored dependency refresh scripts.

The fork starts from the same source tree as published SDK 1.37.0
(`8057ecc256cf6fa2af5254031cd9fa95671e5f5e`). The USB HID behavior on Flex is
unchanged from the previously measured patch. Physical Flex tests reduced the
pre-reply interval from 1.696 to 0.042 s and passed lock/reconnect recovery.
Emulator tests cover overlapping command rejection and pending review responses.
Stax and Nano S Plus hardware validation and timings are pending. See
[the performance report](FLEX_PERFORMANCE.md) for the Flex measurement scope.
