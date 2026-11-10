# Probe 00 — tally

Object: the ceremony floor of one behavior. One program, five hosts, three masses reported separately. This file is the contract. It is the bar for every host.

## Behavior

The program takes one argument, a path. It reads that file as bytes, up to 1,048,576 bytes inclusive. Above that size it writes `file too large` to stderr and exits 1, without parsing.

A zero-byte file writes `empty file` to stderr and exits 1.

The bytes are split on `\n`. A final `\n` does not create an extra line. One trailing `\r` on a line is removed. The line is then an integer or it is rejected.

An integer is an optional leading `+` or `-`, then one or more digits `0` through `9`, and nothing else. The value must fit in a signed 64-bit integer, from `-9223372036854775808` through `9223372036854775807`. Leading zeros are allowed. A space, an underscore, a blank line, a trailing space, and a second sign are rejected.

The running sum must also fit in a signed 64-bit integer. The line that would overflow the sum is rejected.

The first rejected line wins. Stdout is empty on every failure. The message is:

```text
bad line <n>: <text>
```

`<n>` starts at 1. `<text>` is the line after the trailing `\r` was removed. The message ends with one `\n`.

On success the program writes exactly these four lines to stdout, with `\n` and no `\r`, and exits 0:

```text
count <count>
sum <sum>
min <min>
max <max>
```

`<min>` and `<max>` are the smallest and largest values. `<sum>` is their sum. `<count>` is how many lines were accepted. There is no fifth line.

Wrong arguments write `usage: tally <file>` to stderr and exit 1. A path that cannot be opened writes `cannot open <path>` and exits 1. `<path>` is the argument as it was passed. The operating-system reason is not included, so the bytes can match across hosts.

## Masses

- Program text: the behavior file only.
- Project text: the manifest or build file, not including the program text. A lockfile produced by the build is a separate column.
- Vessel: the release binary from the flags in [METHOD.md](../../METHOD.md). Python's interpreter is a shared vessel and is not a binary row.

## Out of this probe

Unicode validation beyond the integer rule, comments, help text, streaming files larger than the cap, and any second behavior. Those are later probes.
