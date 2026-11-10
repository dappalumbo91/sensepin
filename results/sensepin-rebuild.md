# Sensepin score after gauge bytes

Contract `2d4aebf83dec`. Tally behavior 16/16 against probe 00. double, overflow, sum, and bounds matched their declared bytes.

| Program | Residual bytes | Binary |
| --- | ---: | ---: |
| tally | 808 | 178688 |
| sum | 462 | 177664 |
| bounds | 636 | 178176 |
| double | 109 | 146944 |

Gauge runtime: 12537 bytes. Compiler factory: 39338 bytes.

Probe 00 host program text, same tally behavior:

| Host | Program text | Binary |
| --- | ---: | ---: |
| Python | 2816 | shared interpreter |
| C | 4036 | 160768 |
| Rust | 3082 | 151040 |
| Zig | 3628 | 398336 |
| Go | 2200 | 2668032 |

The tally residual is the behavior file. The file, line, and integer gauges live in the runtime, once, and sum and bounds use that same runtime. Each binary still contains the runtime, because this compiler does not share a library across programs. A smaller residual is a program-text result. The earlier row is results/fold-v0.md, contract 281b6f432322. Grades behavior is scored by probes/01-grades/measure.py.
