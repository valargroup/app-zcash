# I/O boundary regressions

Run `python3 tests/io-regression/run.py` in the Ledger build container. These host
tests compile the vendored SDK's actual command decoder, BOLOS handlers, and review
callbacks with scripted OS calls and transport packets. They do not install test
hooks in the application or link test code into device builds.

The tests cover locked application and built-in commands, malformed frames and
wrong classes over every supported packet transport, unlocking, and review-time
rejection without changing the original command's state or reply transport. They
also preserve the legacy behavior when no PIN is configured.

`--sdk-dir PATH` runs the same tests against another SDK source tree. The pristine
1.37.0 release fails the locked-command and review tests. Physical PIN screens,
USB/BLE delivery, and device OS behavior still require hardware checks.
