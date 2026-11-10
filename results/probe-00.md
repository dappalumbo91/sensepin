# Probe 00 score

Contract `2ea9c408fbcb`. 16 cases. Flags are the ones named in METHOD.md.

| Host | Version | Behavior | Program text | Project text | Lockfile | Binary |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Python | Python 3.14.4 | 16/16 | 2816 | 0 | 0 | shared interpreter |
| C | clang version 22.1.5 (https://github.com/llvm/llvm-project 5ea218a153f4d2f815b8244eab3e4b4ba5e00e6c) | 16/16 | 4036 | 0 | 0 | 160768 |
| Rust | rustc 1.95.0 (59807616e 2026-04-14) | 16/16 | 3082 | 60 | 149 | 151040 |
| Zig | 0.15.2 | 16/16 | 3628 | 436 | 0 | 398336 |
| Go | go version go1.26.2 windows/amd64 | 16/16 | 2200 | 22 | 0 | 2668032 |

## Failures

Every host matched the contract.

## What this score can say

Program text is the behavior file. Project text is the manifest. The binary is the release vessel. Python's interpreter stays off this table because the contract named it as a shared vessel.

This probe is one behavior, written once. It can show the ceremony floor. It cannot show repeated sense. Probe 01 scores the second behavior.
