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

## Probe 01

Probe 01 is a grade list. Each row is a name and an integer. The program rejects a bad row with the same style of error as probe 00, then prints the count, the integer mean, the min, the max, and the name tied to the max. The question is how much text the second and third parsed fields cost in each host.

The contract is [probes/01-grades/task.md](probes/01-grades/task.md). The score is [results/probe-01.md](results/probe-01.md), prefix `bd2e38ca5744`. All five hosts matched 25/25. Program text grew by 695 to 969 bytes over each host's tally. The first Sensepin pass had no residual. Gauge `bytes` and `/` were added after that miss, and `fold/examples/grades.sensepin` then matched the same 25 cases in 1576 bytes. The host contract was not edited. On 2026-11-10 the surface words were added: checked `*`, gauge `f64`, gauge `list`, structs, `use`, `while`, and a failure returned from a user function. Tally stayed 16/16 with the same 808-byte residual. Grades stayed 25/25 with the same 1576-byte residual. The tally binary stayed 178688 and the grades binary stayed 179712. The runtime source is 16970 bytes. That score is [results/sensepin-surface.md](results/sensepin-surface.md), contract `d100dcf839db`. On 2026-11-10 the gauge runtime became one shared library, `sensepin.dll`, built with `clang -O2 -shared` and no strip flag. Tally stayed 16/16 with the same 808-byte residual. Grades stayed 25/25 with the same 1576-byte residual. The library is 178688 bytes. The tally exe is 114688 and the grades exe is 115712. One shipped tally is the exe plus the library, 293376 bytes. One shipped grades is 294400 bytes. Two shipped programs are the two exes plus the library once, 409088 bytes. The surface pair of embedded binaries was 358400, so this two-program vessel is larger by 50688 bytes. The tally exe alone is 114688, under the C binary of 160768. The shipped program is the exe plus the library, and that mass is 293376. That score is [results/sensepin-shared.md](results/sensepin-shared.md), contract `c6ecd694d103`. The earlier rows were left as scored.

## Probe 02

Probe 02 is a shelf list. Each row is an item, a quantity, and a unit price. The program rejects a bad row with the same style of error as probe 00, then prints the count, the piece total, the worth, and the item on the first row that is worth the most.

The contract is [probes/02-shelf/task.md](probes/02-shelf/task.md). The score is [results/probe-02.md](results/probe-02.md), prefix `40947a4db99c`. All five hosts and Sensepin matched 30/30. Program text grew over grades by Python +492 (4096), C +947 (5897), Rust +418 (4206), Zig +287 (4884), and Go +618 (3513). The Sensepin residual is 1800 bytes, 224 above the grades residual of 1576, and still under every host program. No new word was added. The shelf exe is 116224. After gauge `map`, the shared library is 179712. One shipped shelf is 295936. The C binary is 161280 and the Rust binary is 151552. Three shipped programs, the tally exe, the grades exe, the shelf exe, and the library once, are 526336. The host contract was not edited.

## Gauge `map`

Gauge `map` is in the language contract. A byte index other than `for` over bytes stays out. The score is [results/sensepin-map.md](results/sensepin-map.md), contract `25a95a30aaef`. Tally stayed 16/16, residual 808, exe 114688. Grades stayed 25/25, residual 1576, exe 115712. `sensepin.dll` is 179712 bytes. One shipped tally is 294400. One shipped grades is 295424. Two shipped programs are 410112, larger than the surface pair 358400 by 51712. `runtime.c` is 20255 bytes. `runtime.h` is 3697 bytes. `foldc.py` is 78581 bytes. The tally, sum, bounds, grades, and shelf exes held the sizes from the desk row. double's exe is 111616. The library holds the map words, so the shipped sums grew with the library.

## The language

Sensepin started on 2026-11-09, after probe 00 matched on all five hosts. Its contract is [fold/SPEC.md](fold/SPEC.md). A row is kept on a named mass only when [fold/score.py](fold/score.py) shows that mass smaller and the behavior matching. The shared-runtime row keeps the behavior and records a larger vessel: two programs are 409088 bytes beside the surface pair of 358400. The map row records two programs at 410112. The gauge runtime is reported beside the residual, so a short program file cannot hide the decoder that holds the library. One shipped program is the exe plus the shared library. `python fold/stress.py` is the hole pass. The working tree keeps `fold/`, `fold_`, and `.sensepin`.
