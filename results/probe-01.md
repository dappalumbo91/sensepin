# Probe 01 score

Contract `bd2e38ca5744`. 25 cases. Flags are the ones named in METHOD.md.

| Host | Version | Behavior | Program text | Delta vs tally | Project text | Lockfile | Binary |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Python | Python 3.14.4 | 25/25 | 3604 | +788 | 0 | 0 | shared interpreter |
| C | clang version 22.1.5 (https://github.com/llvm/llvm-project 5ea218a153f4d2f815b8244eab3e4b4ba5e00e6c) | 25/25 | 4950 | +914 | 0 | 0 | 160768 |
| Rust | rustc 1.95.0 (59807616e 2026-04-14) | 25/25 | 3788 | +706 | 61 | 150 | 151040 |
| Zig | 0.15.2 | 25/25 | 4597 | +969 | 437 | 0 | 400384 |
| Go | go version go1.26.2 windows/amd64 | 25/25 | 2895 | +695 | 23 | 0 | 2669056 |

## Failures

Every host matched the contract.

## What this score can say

The delta column is grades program text minus the probe 00 tally program text for the same host. That is the cost of the name, of the integer as its own field, of the toward-zero mean, and of keeping the first name that holds the max.

File, line split, the integer rule, and the bad-line message are the ceremony probe 00 already paid for. They show up again here. The delta is what the new fields add on top of that copy.

Sensepin v0 is not a host row. A line is one `bytes` value, `i64` parses a whole integer, and the language has no split and no `/`. No residual was scored. A word that would cut a field out of a line, or a word that would divide, would be a new gauge entry with its own score. This contract stays as it was written.
