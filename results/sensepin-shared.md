# Sensepin score after the shared runtime

Contract `c6ecd694d103`. Tally behavior 16/16 against probe 00. double, overflow, sum, and bounds matched their declared bytes.

| Program | Residual bytes | Exe |
| --- | ---: | ---: |
| tally | 808 | 114688 |
| sum | 462 | 113664 |
| bounds | 636 | 113664 |
| double | 109 | 112128 |
| grades | 1576 | 115712 |

Shared library `sensepin.dll`: 178688 bytes. Built with `clang -O2 -shared` and no strip flag.

| Mass | Bytes |
| --- | ---: |
| tally exe + library | 293376 |
| grades exe + library | 294400 |
| tally exe + grades exe + library | 409088 |
| surface tally binary | 178688 |
| surface grades binary | 179712 |
| surface tally + grades | 358400 |

One shipped tally is the exe plus the library, 293376 bytes. One shipped grades is the exe plus the library, 294400 bytes. Two shipped programs are the two exes plus the library once, 409088 bytes.

The surface row, contract `d100dcf839db`, embedded the runtime in each binary: tally 178688, grades 179712, together 358400.

The two-program vessel is 409088 bytes, larger than the surface pair 358400 by 50688 bytes.
One shipped tally is 293376 bytes, larger than the surface tally binary 178688 by 114688 bytes. The library holds every gauge.

Gauge runtime source: `runtime.c` 16598 bytes, `runtime.h` 3031 bytes. Compiler factory: 67549 bytes.

Probe 00 host program text, same tally behavior:

| Host | Program text | Binary |
| --- | ---: | ---: |
| Python | 2816 | shared interpreter |
| C | 4036 | 160768 |
| Rust | 3082 | 151040 |
| Zig | 3628 | 398336 |
| Go | 2200 | 2668032 |

The tally residual is the behavior file. The gauge runtime is one shared library, paid once. An exe holds that program's residual. One shipped program is the exe plus the library. The earlier rows are results/fold-v0.md, contract 281b6f432322, results/sensepin-rebuild.md, contract 2d4aebf83dec, and results/sensepin-surface.md, contract d100dcf839db. Grades behavior is scored by probes/01-grades/measure.py. This row records the grades exe from the same link.
