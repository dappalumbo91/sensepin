# Sensepin v0

Sensepin is the public name. Source files use the extension `.sensepin`. The working tree keeps the directory `fold/`, the compiler `foldc.py`, and the `fold_` prefix.

The language in this folder. A program is an index plus a residual. The index is one phase and the gauges the program names. The residual is the functions. The compiler holds the gauge code and lowers the residual to C. Clang builds that C with `-O2` and no strip flag, the same vessel rule as probe 00.

This file is the contract. `score.py` records its hash. A behavior change here is a new version, not a quiet edit of a scored row.

## Shape

```text
phase console
gauge <name>
fn <name> ... end
```

`phase console` is the first declaration. v0 has that one phase. It means a process with binary stdout and stderr, `argc`/`argv`, and exit code 0 when `main` finishes without `fail`.

A gauge line names one library entry. v0 entries are `args`, `file`, `lines`, `i64`, and `bytes`. Using a word from a gauge that was not named is a compile error. Naming a gauge the program does not use is a compile error. The named set is the index.

`fn main` is required. It has no parameters and no return value. Other functions have typed parameters and one return type. Types are `i64` and `bytes`. A function other than `main` ends with `return`. Calls may recurse. A function returns a value or aborts. It does not hand a failure back to its caller.

```text
fn double(n: i64) -> i64
  return n + n
end
```

## Layout

Indentation is not significant. A comment starts at `#` outside a string and runs to the end of the line. Blank lines are empty. Each remaining line is one declaration or one statement. Blocks opened by `fn`, `if`, and `for` close with a line whose only token is `end`. `if` may contain one `else` line before that `end`.

## Values

`i64` is a signed 64-bit integer. `bytes` is a pointer and a length. A string literal is bytes. The escapes are `\\`, `\"`, and `\n`. No other escape is accepted.

`++` concatenates. An `i64` at either side is rendered in decimal first: no leading `+`, and zero is `0`. The gauge message `out of memory` is written to stderr, with a newline, and the process exits 1, when a concatenation or a line table cannot be stored.

## Failure

`open`, `arg`, `i64(...)`, `+`, `-`, `/`, unary `-`, `len`, `before`, `after`, and `holds` can fail. A failure carries reason bytes.

`expr else expr` uses the left value when the left succeeds. When the left fails, the right expression runs, and the name `reason` there means those bytes. `reason` is a compile error anywhere else.

`fail` writes its bytes, then one `\n`, to stderr and exits 1. It does not return. An operation that fails, and has no `else`, does the same with its own reason. Arithmetic failure and a bad integer have empty reason bytes, so an unhandled one writes a blank stderr line.

## Statements

```text
let <name> = <expr>
set <name> = <expr>
write <expr>
fail <expr>
return <expr>
if <expr> ... end
if <expr> ... else ... end
for <name> in lines(<expr>) ... end
for <name> in bytes(<expr>) ... end
```

`let` binds a name in the current block. A second `let` of the same name in that block is a compile error. An inner block may shadow. `set` assigns a name bound by `let` in a surrounding block. The loop name and function parameters are not assignable.

`write` and `fail` accept `bytes` or `i64`. `write` adds nothing. `if` runs the then-block when the condition, an `i64`, is not 0.

`for` walks the lines of a `bytes` value, or the bytes of a `bytes` value. Over lines, the loop name is a line. `line.text` is `bytes`. `line.n` is the 1-based `i64` line number. A final `\n` does not create another line. One trailing `\r` on a line is removed. `lines("")` walks nothing. Over bytes, the loop name is an `i64` from 0 through 255, one value per byte, in order. `bytes("")` walks nothing. `lines` and `bytes` are legal only as the expression of `for`.

## Gauge `i64`

Named with `gauge i64`. It supplies integer literals, `i64(bytes)`, checked `+`, `-`, and `/`, unary `-`, the comparisons `==` `!=` `<` `>` `<=` `>=`, and decimal rendering.

An integer literal must fit in `i64`. The source form `-9223372036854775808` is that minimum value.

`i64(bytes)` accepts an optional leading `+` or `-`, then one or more digits `0` through `9`, and nothing else. The value must fit in `i64`. Leading zeros are ordinary digits. Any other byte, including a space or an underscore, fails.

`+`, `-`, `/`, and unary `-` fail instead of wrapping. `a - b` when `b` is the minimum `i64` fails, because the negation does not fit. `a / b` truncates toward zero. It fails when `b` is 0, and when `a` is the minimum `i64` and `b` is `-1`, because that quotient does not fit. Comparisons return `i64` 1 or 0. Rendering an `i64` with `write`, `fail`, or `++` uses this gauge.

## Gauge `args`

`argc()` is the process argument count, including the program name. `arg(i)` is argument `i` as bytes. An index outside `0 .. argc()-1` fails with empty reason.

## Gauge `file`

```text
open(path, limit, missing, empty, large)
```

`path`, `missing`, `empty`, and `large` are `bytes`. `limit` is `i64`. On success the result is the file's bytes.

The size is the byte length, measured as a 64-bit count. Above `limit`, or when the length does not fit in the process, the reason is `large` and the bytes are not read. A zero-byte file uses `empty`. A path that cannot be opened, a path that is not a regular file, a path with a zero byte in it, or a read that does not return the whole file, uses `missing` concatenated with `path` and no extra separator. The space in `cannot open ` belongs in the residual's `missing` bytes. A negative `limit` uses `large`.

## Gauge `lines`

`lines(bytes)` is the walk defined under Statements. It is legal only as the expression of `for`.

## Gauge `bytes`

Named with `gauge bytes`. It supplies `len(bytes)`, `before(bytes, bytes)`, `after(bytes, bytes)`, `holds(bytes, bytes)`, and the byte walk defined under Statements.

`len` is the byte count as `i64`. A count that does not fit in `i64` fails. `before` is the bytes before the first match of the separator. `after` is the bytes after that match. `holds` is how many non-overlapping matches the text contains. An empty separator fails. A separator that does not occur makes `before` and `after` fail, and `holds` is 0. The pieces are views of the original bytes.

## Factory limits

Source is UTF-8, at most 1,048,576 bytes, the same ceiling as a probe 00 input. An identifier is an ASCII letter or `_`, then ASCII letters, digits, or `_`, at most 64 characters. A parse deeper than the factory stack is the compile error `source is too deep`.

A user-function call nest deeper than 256 frames writes `call depth` and a newline to stderr and exits 1. 256 frames still return.

The line table for a `for` is released when that loop finishes. File bytes and concatenation storage live until the process exits.

## What v0 does not include

Floats, user structs, modules, multiple files, `*`, first-class lists, and a failure returned from a user function. Gauge `bytes` and `/` are the words probe 01 showed in every host. A later gauge is a new named entry with its own score.

## Vessel

Each program lowers to one C file with the gauge runtime inside it, then `clang -O2`. The binary contains the gauges that program named and the rest of the runtime, because v0 does not share a library across binaries. A smaller residual is a program-text result. It is not yet a smaller vessel. Probe 00 is the behavior bar for `examples/tally.sensepin`.
