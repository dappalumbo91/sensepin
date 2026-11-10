# Probe 02 score

Contract `40947a4db99c`. 30 cases. Flags are the ones named in METHOD.md.

| Host | Version | Behavior | Program text | Delta vs grades | Project text | Lockfile | Binary |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Python | Python 3.14.4 | 30/30 | 4096 | +492 | 0 | 0 | shared interpreter |
| C | clang version 22.1.5 (https://github.com/llvm/llvm-project 5ea218a153f4d2f815b8244eab3e4b4ba5e00e6c) | 30/30 | 5897 | +947 | 0 | 0 | 161280 |
| Rust | rustc 1.95.0 (59807616e 2026-04-14) | 30/30 | 4206 | +418 | 60 | 149 | 151552 |
| Zig | 0.15.2 | 30/30 | 4884 | +287 | 436 | 0 | 401408 |
| Go | go version go1.26.2 windows/amd64 | 30/30 | 3513 | +618 | 22 | 0 | 2670592 |

## Failures

Every host matched the contract.

## What this score can say

The delta column is shelf program text minus the probe 01 grades program text for the same host. That is the cost of the third field and of the checked product of quantity and price.

File, line split, the integer rule, the name alphabet, and the bad-line message are the ceremony the earlier probes already paid for. They show up again here.

Sensepin residual 1800 bytes, exe 116224, shared library 179712, one shipped program 295936, runtime 20255 bytes, behavior 30/30. The language gained no new word for this contract.
The residual is +224 bytes beside the grades residual 1576.
Three shipped programs are tally exe 114688, grades exe 115712, shelf exe 116224, and the library once, together 526336.
The shelf exe is 116224 bytes. One shipped shelf is 295936 bytes. The C binary is 161280 bytes.
The shelf exe is 116224 bytes. One shipped shelf is 295936 bytes. The Rust binary is 151552 bytes.
