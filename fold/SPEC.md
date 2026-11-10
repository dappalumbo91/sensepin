# Sensepin v0

Sensepin is the public name. Source files use the extension `.sensepin`. The working tree keeps the directory `fold/`, the compiler `foldc.py`, and the `fold_` prefix.

The language in this folder. A program is an index plus a residual. The index is one phase and the gauges the program names. The residual is the functions. The compiler holds the gauge code and lowers the residual to C. Clang builds the gauge runtime once as a shared library with `-O2 -shared` and no strip flag, and builds each program with `-O2` and no strip flag, the same vessel rule as probe 00.

This file is the contract. `score.py` records its hash. A behavior change here is a new version, not a quiet edit of a scored row.

## Shape

```text
phase console
gauge <name>
fn <name> ... end
```

`phase console` is the first declaration. v0 has that one phase. It means a process with binary stdout and stderr, `argc`/`argv`, and exit code 0 when `main` finishes without `fail`.

A gauge line names one library entry. v0 entries are `args`, `file`, `lines`, `i64`, `bytes`, `f64`, `list`, and `map`. Using a word from a gauge that was not named is a compile error. Naming a gauge the program does not use is a compile error. The named set is the index.

`fn main` is required in the root file. It has no parameters and no return value. Other functions have typed parameters and one return type. Types are `i64`, `f64`, `bytes`, `list` of a type, `map` of a key type to a value type, and struct names. A function other than `main` ends with `return` or `fail`. Calls may recurse. A function returns a value, or returns a failure to its caller.

```text
fn double(n: i64) -> i64
  return n + n
end
```

## Layout

Indentation is not significant. A comment starts at `#` outside a string and runs to the end of the line. Blank lines are empty. Each remaining line is one declaration or one statement. Blocks opened by `fn`, `if`, `for`, `while`, and `struct` close with a line whose only token is `end`. `if` may contain one `else` line before that `end`.

After `phase console`, a file may contain `gauge`, `use`, `struct`, and `fn` in any order.

## Values

`i64` is a signed 64-bit integer. `f64` is an IEEE-754 binary64 value. `bytes` is a pointer and a length. A string literal is bytes. The escapes are `\\`, `\"`, and `\n`. No other escape is accepted.

`++` concatenates. An `i64` at either side is rendered in decimal first: no leading `+`, and zero is `0`. An `f64` is rendered as below. The gauge message `out of memory` is written to stderr, with a newline, and the process exits 1, when a concatenation, a line table, a list copy, or a map copy cannot be stored.

## Failure

`open`, `save`, `arg`, `i64(...)`, `+`, `-`, `*`, `/`, unary `-`, `len`, `before`, `after`, `holds`, `byte`, `at`, `set_byte`, `get`, an `f64` operation, and a user-function call can fail. A failure carries reason bytes.

`expr else expr` uses the left value when the left succeeds. When the left fails, the right expression runs, and the name `reason` there means those bytes. `reason` is a compile error anywhere else.

`fail` in `main` writes its bytes, then one `\n`, to stderr and exits 1. `fail` in another function returns that failure to the caller. An operation in `main` that fails, and has no `else`, writes its reason and exits the same way. An operation in another function that fails, and has no `else`, returns that failure to its caller. Arithmetic failure, a bad integer, a non-finite `f64`, and an `at` outside the list have empty reason bytes, so an unhandled one that reaches `main` writes a blank stderr line.

## Statements

```text
let <name> = <expr>
let <name>: <type> = <expr>
set <name> = <expr>
write <expr>
fail <expr>
return <expr>
if <expr> ... end
if <expr> ... else ... end
while <expr> ... end
for <name> in lines(<expr>) ... end
for <name> in bytes(<expr>) ... end
for <name> in <list> ... end
for <name> in <map> ... end
```

`let` binds a name in the current block. A second `let` of the same name in that block is a compile error. An inner block may shadow. A `let` may name a type. The expression must have that type. `list()` with no elements takes its type from that annotation, from the parameter or return it fills, or from the other side of `else`. `map()` with no pairs takes its type the same way. `set` assigns a name bound by `let` in a surrounding block. The loop name and function parameters are not assignable.

`write` and `fail` accept `bytes`, `i64`, or `f64`. `write` adds nothing. `if` and `while` run the body when the condition, an `i64`, is not 0. `while` tests the condition again after each pass.

`for` walks the lines of a `bytes` value, the bytes of a `bytes` value, the elements of a list, or the keys of a map. Over lines, the loop name is a line. `line.text` is `bytes`. `line.n` is the 1-based `i64` line number. A final `\n` does not create another line. One trailing `\r` on a line is removed. `lines("")` walks nothing. Over bytes, the loop name is an `i64` from 0 through 255, one value per byte, in order. `bytes("")` walks nothing. `lines` and `bytes` are legal only as the expression of `for`. Over a list, the loop name has the element type. Over a map, the loop name has the key type, and the walk follows insertion order.

## Gauge `i64`

Named with `gauge i64`. It supplies integer literals, `i64(bytes)`, `i64(f64)`, checked `+`, `-`, `*`, and `/`, unary `-`, the comparisons `==` `!=` `<` `>` `<=` `>=`, and decimal rendering.

An integer literal must fit in `i64`. The source form `-9223372036854775808` is that minimum value.

`i64(bytes)` accepts an optional leading `+` or `-`, then one or more digits `0` through `9`, and nothing else. The value must fit in `i64`. Leading zeros are ordinary digits. Any other byte, including a space or an underscore, fails. `i64(f64)` truncates toward zero. It fails when the value is not finite or does not fit in `i64`.

`+`, `-`, `*`, `/`, and unary `-` fail instead of wrapping. `a - b` when `b` is the minimum `i64` fails, because the negation does not fit. `a * b` fails when the product does not fit, including the minimum `i64` multiplied by `-1`. `a / b` truncates toward zero. It fails when `b` is 0, and when `a` is the minimum `i64` and `b` is `-1`, because that quotient does not fit. Comparisons return `i64` 1 or 0. Rendering an `i64` with `write`, `fail`, or `++` uses this gauge.

## Gauge `args`

`argc()` is the process argument count, including the program name. `arg(i)` is argument `i` as bytes. An index outside `0 .. argc()-1` fails with empty reason.

## Gauge `file`

```text
open(path, limit, missing, empty, large)
```

`path`, `missing`, `empty`, and `large` are `bytes`. `limit` is `i64`. On success the result is the file's bytes.

The size is the byte length, measured as a 64-bit count. Above `limit`, or when the length does not fit in the process, the reason is `large` and the bytes are not read. A zero-byte file uses `empty`. A path that cannot be opened, a path that is not a regular file, a path with a zero byte in it, or a read that does not return the whole file, uses `missing` concatenated with `path` and no extra separator. The space in `cannot open ` belongs in the residual's `missing` bytes. A negative `limit` uses `large`.

`save(path, data)` writes `data` to `path`, replacing an existing file, and returns the byte count as `i64`. A path with a zero byte in it, a path that cannot be created, or a write that does not finish, fails with empty reason. An empty `data` creates an empty file and returns 0.

## Gauge `lines`

`lines(bytes)` is the walk defined under Statements. It is legal only as the expression of `for`.

## Gauge `bytes`

Named with `gauge bytes`. It supplies `len(bytes)`, `before(bytes, bytes)`, `after(bytes, bytes)`, `holds(bytes, bytes)`, `byte(i64)`, `at(bytes, i64)`, `set_byte(bytes, i64, i64)`, and the byte walk defined under Statements.

`len` is the byte count as `i64`. A count that does not fit in `i64` fails. `before` is the bytes before the first match of the separator. `after` is the bytes after that match. `holds` is how many non-overlapping matches the text contains. An empty separator fails. A separator that does not occur makes `before` and `after` fail, and `holds` is 0. The pieces are views of the original bytes. `byte` is a one-byte value. The argument must be from 0 through 255. `at` is the byte at a 0-based index, as `i64` from 0 through 255. An index below 0 or past the last byte fails with empty reason. `set_byte` returns a new byte string with that index replaced. The earlier bytes stay as they were. An index outside the string, or a value outside 0 through 255, fails with empty reason.

## Gauge `f64`

Named with `gauge f64`. A literal has digits, a dot, and digits, as in `1.5` or `1.0`. The value is IEEE-754 binary64.

`+`, `-`, `*`, `/`, and unary `-` apply when both sides are `f64`. An `i64` and an `f64` stay separate types. The operation fails when the result is not finite, including division by zero. A result that underflows to zero is zero. `f64(i64)` is the IEEE conversion. It can drop low bits of an integer wider than the 53-bit significand. Comparisons of two `f64` values return `i64` 1 or 0.

`write`, `fail`, and `++` render a finite `f64` with seventeen significant digits. When that text has no decimal point and no exponent, `.0` is appended. Zero, including negative zero, renders as `0.0`.

## Gauge `list`

Named with `gauge list`. A list holds one element type. The element may be `i64`, `f64`, `bytes`, a struct, a list, or a map. `list(a, b)` uses the type of its elements. Every element has that same type. `len(list)` is the count as `i64`, and it fails when the count does not fit. `at(list, i)` is the element at a 0-based `i64` index. An index below 0 or past the last element fails with empty reason. `push(list, value)` returns a new list with `value` at the end. The earlier list stays as it was. `for` walks the elements in order.

## Gauge `map`

Named with `gauge map`. A map holds one key type and one value type. The key is `i64`, `f64`, or `bytes`. The value may be `i64`, `f64`, `bytes`, a list, a struct, or a map. `map(k, v, k, v)` uses the types of its first pair. Every pair has those same types. An odd argument count is a compile error. A repeated key keeps the first position and takes the later value. `len(map)` is the count as `i64`, and it fails when the count does not fit. `get(map, key)` is the value stored at that key. A missing key fails with empty reason. `has(map, key)` is `i64` 1 when the key is present and `i64` 0 when it is not, and it does not fail. `put(map, key, value)` returns a new map. The earlier map stays as it was. Replacing a key keeps that key's first position. `for` walks the keys in insertion order. Two `f64` keys compare equal when their values compare equal, so `0.0` and `-0.0` are one key. Two `bytes` keys compare equal when their lengths match and their bytes match. `put` copies the key and the value. Bytes, lists, and maps inside a copied value still share their storage.

## Structs

```text
struct point
  x: i64
  y: i64
end
```

`point(1, 2)` builds a value, one argument per field, in order. `name.field` reads a field. A field may itself be read when the receiver is a field, a call, or a name. A struct may contain `i64`, `f64`, `bytes`, a list, a map, or another struct. A struct that contains itself through struct fields is a compile error. A field may be a list of that same struct, or a map whose value is that same struct. `push` copies the element. `put` copies the key and the value. Bytes inside a struct still share their storage.

## Use

```text
use "twice.sensepin"
```

`use` reads another `.sensepin` file. The path is relative to the file that writes the `use`, and it stays inside that file's directory. The used file starts with `phase console` and may omit `fn main`. Its gauges, structs, and functions join the program. Naming the same gauge in more than one file keeps one entry. A repeated function name, a repeated struct name, a cycle, or a missing file is a compile error. The root file still requires `fn main`.

## Factory limits

Source is UTF-8, at most 1,048,576 bytes, the same ceiling as a probe 00 input. An identifier is an ASCII letter or `_`, then ASCII letters, digits, or `_`, at most 64 characters. A parse deeper than the factory stack is the compile error `source is too deep`.

A user-function call nest deeper than 256 frames writes `call depth` and a newline to stderr and exits 1. 256 frames still return.

The line table for a `for` over lines is released when that loop finishes. File bytes, concatenation storage, list storage, and map storage live until the process exits.

## What v0 does not include

`*`, `f64`, `list`, `map`, structs, `use`, `while`, a failure returned from a user function, `at` on bytes, `byte`, `set_byte`, `save`, and one shared gauge library are in this contract. A later gauge is a new named entry with its own score.

## Desk

`python fold/sensepin.py run <file.sensepin>` compiles that file, links `sensepin.dll`, and runs the exe. `build` writes an exe and places the library beside it. `check` reports the first compile error. `install.ps1` copies this desk onto the user account and adds it to the user Path. `fold/lsp.py` speaks the language server protocol and publishes that compile error as a diagnostic. `editors/vscode` starts that server for `.sensepin` files.

## Vessel

The gauge runtime is one shared library, `sensepin.dll`, built with `clang -O2 -shared` and no strip flag. Each program lowers to one C file and links that library, still with `clang -O2` and no strip flag. The library holds every gauge. A program exe holds that program's residual. The shared library is paid once for every program that links it. One shipped program is the exe plus the library. Two shipped programs are the two exes plus the library once. Probe 00 is the behavior bar for `examples/tally.sensepin`.
