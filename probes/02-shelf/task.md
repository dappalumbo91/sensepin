# Probe 02 — shelf

Object: a third program a person already knows, and the text a third field costs on top of probe 01. A shelf row is an item, a quantity, and a unit price. The program rejects a bad row the way tally does, then prints how many rows were kept, how many pieces that is, what those rows are worth, and the item on the first row that is worth the most. This file is the contract. It is the bar for every host.

## Behavior

The program takes one argument, a path. It reads that file as bytes, up to 1,048,576 bytes inclusive. Above that size it writes `file too large` to stderr and exits 1, without parsing.

A zero-byte file writes `empty file` to stderr and exits 1.

The bytes are split on `\n`. A final `\n` does not create an extra line. One trailing `\r` on a line is removed. The line is then one shelf row, or it is rejected.

A shelf row contains exactly two bytes ` ` (U+0020). Splitting on those two bytes yields three fields: a name, a quantity, and a price. The name is one or more bytes from `A-Z`, `a-z`, `0-9`, and `_`. The quantity and the price are each probe 00's integer: an optional leading `+` or `-`, then one or more digits `0` through `9`, and nothing else. Each value must fit in a signed 64-bit integer, from `-9223372036854775808` through `9223372036854775807`. Leading zeros are allowed. A missing field, an extra field, an empty field, a byte outside the name alphabet, a blank line, and a bad integer are rejected.

The line value is the quantity times the price. Multiplication that does not fit is rejected. Zero times any fitted integer is 0, including zero times `-9223372036854775808`. The minimum integer times `-1` is rejected. The minimum integer times `1` is the minimum integer.

The running piece count is the sum of the quantities. The running worth is the sum of the line values. A sum that does not fit is rejected on the line that would overflow it.

The first rejected line wins. Stdout is empty on every failure. The message is:

```text
bad line <n>: <text>
```

`<n>` starts at 1. `<text>` is the line after the trailing `\r` was removed. The message ends with one `\n`.

On success the program writes exactly these four lines to stdout, with `\n` and no `\r`, and exits 0:

```text
count <count>
pieces <pieces>
value <value>
item <item>
```

`<count>` is how many rows were accepted. `<pieces>` is the sum of the quantities. `<value>` is the sum of the line values. `<item>` is the name on the first row whose line value equals the largest line value. A later row with the same line value keeps the earlier name. There is no fifth line.

Wrong arguments write `usage: shelf <file>` to stderr and exit 1. A path that cannot be opened writes `cannot open <path>` and exits 1. `<path>` is the argument as it was passed. The operating-system reason is not included, so the bytes can match across hosts.

## Masses

Program text is the behavior file. Project text is the manifest or build file, not including the program text. A lockfile produced by the build is a separate column. The host vessel is the release binary from the flags in [METHOD.md](../../METHOD.md), with the program name `shelf`. Python's interpreter is a shared vessel and is not a binary row.

Sensepin reports four masses for this program: the residual, the exe, the one shared library `sensepin.dll`, and one shipped program, which is the exe plus that library. The three-program vessel is the tally exe, the grades exe, the shelf exe, and that library once.

## Out of this probe

A fourth field, comments, Unicode names, grouping the same name across rows, maps, and any new Sensepin word. Sensepin meets this contract with the language as it stands, or the row is a miss. The contract is not loosened so a row can pass.
