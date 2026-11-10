# Probe 01 — grades

Object: the text a second field and a third field cost on top of probe 00. Probe 00 parsed one field, the whole line as an integer. This probe parses a name and an integer on each line. This file is the contract. It is the bar for every host.

## Behavior

The program takes one argument, a path. It reads that file as bytes, up to 1,048,576 bytes inclusive. Above that size it writes `file too large` to stderr and exits 1, without parsing.

A zero-byte file writes `empty file` to stderr and exits 1.

The bytes are split on `\n`. A final `\n` does not create an extra line. One trailing `\r` on a line is removed. The line is then one grade, or it is rejected.

A grade is a name, one byte ` ` (U+0020), and an integer, with nothing else on the line. The name is one or more bytes from `A-Z`, `a-z`, `0-9`, and `_`. The integer is probe 00's integer: an optional leading `+` or `-`, then one or more digits `0` through `9`, and nothing else. The value must fit in a signed 64-bit integer, from `-9223372036854775808` through `9223372036854775807`. Leading zeros are allowed. A missing space, a second space, an empty name, a byte outside the name alphabet, a blank line, and a bad integer are rejected.

The running sum must also fit in a signed 64-bit integer. The line that would overflow the sum is rejected.

The first rejected line wins. Stdout is empty on every failure. The message is:

```text
bad line <n>: <text>
```

`<n>` starts at 1. `<text>` is the line after the trailing `\r` was removed. The message ends with one `\n`.

On success the program writes exactly these five lines to stdout, with `\n` and no `\r`, and exits 0:

```text
count <count>
mean <mean>
min <min>
max <max>
name <name>
```

`<count>` is how many lines were accepted. `<min>` and `<max>` are the smallest and largest values. `<mean>` is the sum divided by the count, truncated toward zero. The sum of `-1` and `0` has mean `0`. `<name>` is the name on the first line whose value equals `<max>`. A later line with the same value keeps the earlier name. There is no sixth line.

Wrong arguments write `usage: grades <file>` to stderr and exit 1. A path that cannot be opened writes `cannot open <path>` and exits 1. `<path>` is the argument as it was passed. The operating-system reason is not included, so the bytes can match across hosts.

## Masses

Program text is the behavior file. Project text is the manifest or build file, not including the program text. A lockfile produced by the build is a separate column. The vessel is the release binary from the flags in [METHOD.md](../../METHOD.md), with the program name `grades` where probe 00 used `tally`. Python's interpreter is a shared vessel and is not a binary row.

## Out of this probe

A further field, comments, Unicode names, a shared library, and any new Sensepin word. Sensepin meets this contract with the language as it stands, or the row is a miss. The contract is not loosened so a row can pass.
