# Sensepin

Author: Damian Arthur Palumbo. https://github.com/dappalumbo91/sensepin

The desktop folder is Source fold. The language is Sensepin: one sense across many forms, pinned to a law. A program names a phase and the gauges it uses, then writes the residual the law does not rebuild. Source files use `.sensepin`. The working tree keeps the directory `fold/`, the compiler `foldc.py`, and the `fold_` prefix. The license is Apache-2.0, the same license as the other public repositories on this account.

This folder asks why a program takes the space it takes, whether that space can be cut without changing the behavior, and whether a language of our own is the cut that holds. Python, C, Rust, Zig, and Go are the first hosts. Haskell, TypeScript, and Lean are later hosts, because each one measures a different mass.

The split comes from the compressor. In [fsot-residual](https://github.com/dappalumbo91/fsot-residual) the compressed state is phase, zoom, gauge, and the residual the law does not fix. The decoder already holds the engine. Source is large when the text restates a gauge the reader and the compiler already hold. The residual is the part they do not hold.

Probe 00 measured that floor. Sensepin is the language built from it. The compiler lowers a program to C. The host program of the same behavior stays the size bar. The public FSOT repositories are the reference for how a build is made. They are not copied into this folder, and this folder does not retune their pins. `python fold/stress.py` is the hole pass.

## Read in this order

| File | What it is |
| --- | --- |
| [REFERENCE.md](REFERENCE.md) | Which FSOT repositories this project reads, and what each one already built. |
| [METHOD.md](METHOD.md) | How a mass is named, scored, and either kept or left as a miss. |
| [probes/00-tally/task.md](probes/00-tally/task.md) | The first contract. Written before the score. |
| [results/probe-00.md](results/probe-00.md) | The score of that contract, once `measure.py` has run. |
| [probes/01-grades/task.md](probes/01-grades/task.md) | The grade-list contract. A name and an integer on each row. |
| [results/probe-01.md](results/probe-01.md) | The score of that contract, once its `measure.py` has run. |
| [fold/SPEC.md](fold/SPEC.md) | The Sensepin language contract. |
| [results/fold-v0.md](results/fold-v0.md) | The score of the first Sensepin programs, once `fold/score.py` has run. |

## First command

```text
python probes/00-tally/measure.py
python probes/01-grades/measure.py
python fold/score.py
```

Each scorer rebuilds every host, runs the same files through them, and writes that probe's result. A host that disagrees with the contract is a failed row. The contract is not edited to fit a host.
