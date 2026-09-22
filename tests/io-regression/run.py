"""Compile the real SDK I/O sources against a scripted host OS and transport."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--sdk-dir", type=Path, default=root / "vendor/ledger_device_sdk")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ledger-io-tests-") as directory:
        work = Path(directory)
        # Preserve the SDK's module tree under mod.rs so #[path] resolves its children.
        shutil.copytree(args.sdk_dir / "src/io_new", work / "sdk_io")
        shutil.copyfile(args.sdk_dir / "src/io_new.rs", work / "sdk_io/mod.rs")
        shutil.copyfile(args.sdk_dir / "src/seph.rs", work / "sdk_seph.rs")
        source = (Path(__file__).with_name("pin.rs")).read_text()
        source = source.replace("../../vendor/ledger_device_sdk/src/io_new.rs", "sdk_io/mod.rs")
        source = source.replace("../../vendor/ledger_device_sdk/src/seph.rs", "sdk_seph.rs")
        (work / "pin.rs").write_text(source)
        binary = work / "pin-tests"
        subprocess.run(["rustc", "--edition=2024", "--test", str(work / "pin.rs"),
                        "-o", str(binary)], check=True)
        subprocess.run([str(binary), "--test-threads=1"], check=True)
        shutil.copyfile(root / "src/swap/panic_handler.rs", work / "swap_panic_handler.rs")
        shutil.copyfile(Path(__file__).with_name("swap_panic.rs"), work / "swap_panic.rs")
        for failure in (False, True):
            binary = work / "swap-panic"
            command = ["rustc", "--edition=2024", "-C", "panic=abort",
                       str(work / "swap_panic.rs"), "-o", str(binary)]
            if failure:
                command += ["--cfg", "send_failure"]
            subprocess.run(command, check=True)
            subprocess.run([str(binary)], check=True)
            print(f"Swap panic returns to Exchange with send_failure={failure}", flush=True)


if __name__ == "__main__":
    main()
