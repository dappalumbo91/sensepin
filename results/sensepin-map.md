# Sensepin score after gauge map

Contract `25a95a30aaef`. Tally behavior 16/16 against probe 00. double, overflow, sum, and bounds matched their declared bytes.

| Program | Residual bytes | Exe |
| --- | ---: | ---: |
| tally | 808 | 114688 |
| sum | 462 | 113664 |
| bounds | 636 | 113664 |
| double | 109 | 111616 |
| grades | 1576 | 115712 |

Shared library `sensepin.dll`: 179712 bytes. Built with `clang -O2 -shared` and no strip flag.

| Mass | Bytes |
| --- | ---: |
| tally exe + library | 294400 |
| grades exe + library | 295424 |
| tally exe + grades exe + library | 410112 |
| surface tally binary | 178688 |
| surface grades binary | 179712 |
| surface tally + grades | 358400 |

One shipped tally is the exe plus the library, 294400 bytes. One shipped grades is the exe plus the library, 295424 bytes. Two shipped programs are the two exes plus the library once, 410112 bytes.

The surface row, contract `d100dcf839db`, embedded the runtime in each binary: tally 178688, grades 179712, together 358400.

The two-program vessel is 410112 bytes, larger than the surface pair 358400 by 51712 bytes.
One shipped tally is 294400 bytes, larger than the surface tally binary 178688 by 115712 bytes. The library holds every gauge.

Gauge runtime source: `runtime.c` 20255 bytes, `runtime.h` 3697 bytes. Compiler factory: 78581 bytes.

Probe 00 host program text, same tally behavior:

| Host | Program text | Binary |
| --- | ---: | ---: |
| Python | 2816 | shared interpreter |
| C | 4036 | 160768 |
| Rust | 3082 | 151040 |
| Zig | 3628 | 398336 |
| Go | 2200 | 2668032 |

The tally residual is the behavior file. The gauge runtime is one shared library, paid once. An exe holds that program's residual. One shipped program is the exe plus the library. Gauge `map` is in this contract. A byte index other than `for` over bytes stays out. The desk command, the Windows installer, and editor diagnostics are in this tree. Probe 02 shelf is results/probe-02.md, contract 40947a4db99c. The earlier rows are results/fold-v0.md, contract 281b6f432322, results/sensepin-rebuild.md, contract 2d4aebf83dec, results/sensepin-surface.md, contract d100dcf839db, results/sensepin-shared.md, contract c6ecd694d103, and results/sensepin-desk.md, contract 803bc794ee66. Grades behavior is scored by probes/01-grades/measure.py. This row records the grades exe from the same link.
