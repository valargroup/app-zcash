# Flex USB reply patch

The vendored ledger_device_sdk is crates.io 1.37.0, upstream source commit
8057ecc256cf6fa2af5254031cd9fa95671e5f5e. The only changes are a fast_usb_reply
feature and a condition in io_legacy.rs that skips the pre-reply io_rx for Flex
USB HID. Other targets and transports keep their existing behavior. Receive-loop
event servicing and the command-in-progress review guard are unchanged.

The app enables the feature through its workspace dependency. The vendor pin and
patch are registered in pinned_deps.sh so dependency refresh retains the change.
No diagnostic review/reply hooks or transaction timing transport are included.

Historical physical tests reduced the pre-reply interval from 1.696 to 0.042 s
and passed locked-device/reconnect recovery. Emulator tests cover review-time
command rejection and preserve pending review approval/rejection. See
../docs/FLEX_PERFORMANCE.md for timing scope. BLE and non-Flex paths are unchanged
by the gate; this does not establish a measured speedup for those transports.
