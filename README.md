# Sensepin

Author: Damian Arthur Palumbo. https://github.com/dappalumbo91/sensepin

The desktop folder is Source fold. The language is Sensepin: one sense across many forms, pinned to a law. A program names a phase and the gauges it uses, then writes the residual the law does not rebuild. Source files use `.sensepin`. The working tree keeps the directory `fold/`, the `fold_` prefix, and `foldc.py` for the scored host path. The language compiler is `fold/compiler.sensepin`. The license is Apache-2.0, the same license as the other public repositories on this account.

This folder asks why a program takes the space it takes, whether that space can be cut without changing the behavior, and whether a language of our own is the cut that holds. Python, C, Rust, Zig, and Go are the first hosts. Haskell, TypeScript, and Lean are later hosts, because each one measures a different mass.

The split comes from the compressor. In [fsot-residual](https://github.com/dappalumbo91/fsot-residual) the compressed state is phase, zoom, gauge, and the residual the law does not fix. The decoder already holds the engine. Source is large when the text restates a gauge the reader and the compiler already hold. The residual is the part they do not hold.

Probe 00 measured that floor. Sensepin is the language built from it. The language compiler is `fold/compiler.sensepin`. The desk calls the image that compiler produces. The scored rows on this page were measured with `foldc.py`, which lowers a program to C and links one shared gauge library. One shipped program on those rows is the exe plus that library. The host program of the same behavior stays the size bar. The public FSOT repositories are the reference for how a build is made. They are not copied into this folder, and this folder does not retune their pins. `python fold/stress.py` is the hole pass.

## Read in this order

| File | What it is |
| --- | --- |
| [REFERENCE.md](REFERENCE.md) | Which FSOT repositories this project reads, and what each one already built. |
| [METHOD.md](METHOD.md) | How a mass is named, scored, and either kept or left as a miss. |
| [probes/00-tally/task.md](probes/00-tally/task.md) | The first contract. Written before the score. |
| [results/probe-00.md](results/probe-00.md) | The score of that contract, once `measure.py` has run. |
| [probes/01-grades/task.md](probes/01-grades/task.md) | The grade-list contract. A name and an integer on each row. |
| [results/probe-01.md](results/probe-01.md) | The score of that contract, once its `measure.py` has run. |
| [probes/02-shelf/task.md](probes/02-shelf/task.md) | The shelf contract. An item, a quantity, and a price. |
| [results/probe-02.md](results/probe-02.md) | The score of that contract. 30/30. Contract `40947a4db99c`. |
| [fold/SPEC.md](fold/SPEC.md) | The Sensepin language contract. |
| [results/fold-v0.md](results/fold-v0.md) | The first Sensepin score, contract `281b6f432322`. Left as it was scored. |
| [results/sensepin-rebuild.md](results/sensepin-rebuild.md) | Tally scored again after gauge `bytes` and `/`. |
| [results/sensepin-surface.md](results/sensepin-surface.md) | Tally scored again after `*`, `f64`, lists, structs, `use`, `while`, and a failure a function can hand back. Contract `d100dcf839db`. |
| [results/sensepin-shared.md](results/sensepin-shared.md) | Tally scored again after the gauge runtime became one shared library. Contract `c6ecd694d103`. One shipped program is the exe plus `sensepin.dll`. |
| [results/sensepin-desk.md](results/sensepin-desk.md) | Tally scored again after the desk command, the installer, and editor diagnostics. Contract `803bc794ee66`. |
| [results/sensepin-map.md](results/sensepin-map.md) | Tally scored again after gauge `map`. Contract `25a95a30aaef`. |

## First command

```text
python probes/00-tally/measure.py
python probes/01-grades/measure.py
python probes/02-shelf/measure.py
python fold/score.py
python fold/sensepin.py run fold/examples/shelf.sensepin <file>
```

`install.ps1` copies the desk to `%LOCALAPPDATA%\Sensepin` and adds `sensepin` to the user Path. `fold/lsp.py` publishes the compiler's first error. The VS Code extension is [editors/vscode](editors/vscode).

Each scorer rebuilds every host, runs the same files through them, and writes that probe's result. A host that disagrees with the contract is a failed row. The contract is not edited to fit a host.
