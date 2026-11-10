# Method

A row is a pass only when the named mass gets smaller and the behavior matches the contract that was written first. A smaller file that does a different job is a different object.

## Three masses

| Mass | What is counted | What is not counted |
| --- | --- | --- |
| Program text | The files a person writes for the behavior. | Comments added only to pad or to shrink a measurement. The straightforward program. |
| Project text | Manifests and build files required to build or run. Lockfiles are their own column. | The compiler, the standard-library source, and this folder's scorer. |
| Vessel | The release binary produced by the declared flags. | A strip pass that was not in the contract. The installed interpreter, which is recorded as a shared vessel and is not a binary row. |

Python has program text and no binary of its own. The interpreter is the shared vessel. C, Rust, Zig, and Go have a binary a person can copy without installing the language. Those rows are not ranked against each other until the contract says which mass is the bar.

## Rules

- Name the object before the run. Probe 00's object is the ceremony floor of one small behavior, measured separately as program text, project text, and vessel.
- Write the contract in `task.md` before scoring. The scorer records a hash of that file. Editing the contract after the score is a new probe.
- Every host runs the same bytes in and must produce the same bytes out, including the error text and the exit code.
- A host that fails the contract is a failed row. The contract is not loosened so the row can pass.
- A miss stays a miss. A later idea does not rewrite an earlier score.
- Zero arbitrary free parameters. A syntax knob added because one sample got shorter stays out. A gauge entry is legal when the probes showed that shape repeating and the rebuilt program matches.
- The host program of the same behavior is the size bar for any notation we add. The notation has to rebuild the program, the way a decoder has to rebuild the song.
- This folder does not retune FSOT pins, and it does not copy `vendor/fsot_compute.py`.

## Declared flags for probe 00

| Host | Build |
| --- | --- |
| Python 3.14 | No build. Run the file. |
| C | `clang -O2`, no strip flag. |
| Rust | `cargo build --release --offline`. Edition 2021. No dependencies. |
| Zig 0.15 | `zig build -Doptimize=ReleaseFast`. |
| Go | `go build -o tally.exe .` Default flags. No `-ldflags` strip. |

## Hypotheses

These are unnamed until a probe scores them. They are the list of places the mass might sit.

| Id | Statement |
| --- | --- |
| H1 | Most of a small program's project is ceremony: the manifest and the build file, not the behavior. |
| H2 | The same sense is written again because the language has no single name for it. |
| H3 | The contract is restated at every call because the compiler is not trusted to hold it. |
| H4 | The vessel is outside the file. Source looks small because the interpreter is assumed. |
| H5 | The lockfile and the dependency closure dominate the program text. |
| H6 | Source can shrink while the binary grows. They are different objects. |
| H7 | Generated or already-coded text does not shrink. A macro expansion is that object. |

Probe 00 can speak to H1, H4, and H6. It is one behavior, once. It cannot speak to H2. Repetition needs a second copy of the same shape.

## Next contract, not yet a probe

Probe 01 is a grade list. Each row is a name and an integer. The program rejects a bad row with the same style of error as probe 00, then prints the count, the integer mean, the min, the max, and the name tied to the max. The new question is how much text the second and third parsed fields cost in each host. Probe 00 is scored. Probe 01 is still unwritten.

## The language

Sensepin started on 2026-11-09, after probe 00 matched on all five hosts. Its contract is [fold/SPEC.md](fold/SPEC.md). A row is kept on a named mass only when [fold/score.py](fold/score.py) shows that mass smaller and the behavior matching. The gauge runtime is reported beside the residual, so a short program file cannot hide the decoder that holds the library. `python fold/stress.py` is the hole pass. The working tree keeps `fold/`, `fold_`, and `.fold`.
