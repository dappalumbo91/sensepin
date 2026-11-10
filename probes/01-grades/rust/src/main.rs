//! Probe 01 grades. Contract: probes/01-grades/task.md.

use std::env;
use std::fs;
use std::io::{self, Write};
use std::process::ExitCode;

const MAX_BYTES: usize = 1_048_576;

fn emit(message: &str) -> ExitCode {
    eprintln!("{message}");
    ExitCode::from(1)
}

fn name_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

fn parse_i64(text: &str) -> Option<i64> {
    if text.is_empty() || text == "+" || text == "-" {
        return None;
    }
    let body = if text.starts_with('+') || text.starts_with('-') {
        &text[1..]
    } else {
        text
    };
    if body.is_empty() || !body.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    text.parse::<i64>().ok()
}

fn parse_grade(line: &[u8]) -> Option<(usize, i64)> {
    let space = line.iter().position(|byte| *byte == b' ')?;
    if space == 0 || line[space + 1..].contains(&b' ') {
        return None;
    }
    if !line[..space].iter().copied().all(name_byte) {
        return None;
    }
    let text = std::str::from_utf8(&line[space + 1..]).ok()?;
    let value = parse_i64(text)?;
    Some((space, value))
}

fn bad_line(line_no: i64, line: &[u8]) -> ExitCode {
    let mut err = io::stderr().lock();
    write!(err, "bad line {line_no}: ").ok();
    err.write_all(line).ok();
    writeln!(err).ok();
    ExitCode::from(1)
}

fn main() -> ExitCode {
    let mut args = env::args();
    let _program = args.next();
    let Some(path) = args.next() else {
        return emit("usage: grades <file>");
    };
    if args.next().is_some() {
        return emit("usage: grades <file>");
    }

    let meta = match fs::metadata(&path) {
        Ok(meta) => meta,
        Err(_) => {
            eprintln!("cannot open {path}");
            return ExitCode::from(1);
        }
    };
    if meta.len() > MAX_BYTES as u64 {
        return emit("file too large");
    }
    if meta.len() == 0 {
        return emit("empty file");
    }
    let data = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(_) => {
            eprintln!("cannot open {path}");
            return ExitCode::from(1);
        }
    };

    let mut count: i64 = 0;
    let mut sum: i64 = 0;
    let mut low: i64 = 0;
    let mut high: i64 = 0;
    let mut max_at = 0usize;
    let mut max_len = 0usize;
    let mut any = false;
    let mut line_no: i64 = 1;
    let mut start = 0usize;
    while start < data.len() {
        let mut end = start;
        while end < data.len() && data[end] != b'\n' {
            end += 1;
        }
        let mut limit = end;
        if limit > start && data[limit - 1] == b'\r' {
            limit -= 1;
        }
        let line = &data[start..limit];
        let Some((space, value)) = parse_grade(line) else {
            return bad_line(line_no, line);
        };
        let Some(next) = sum.checked_add(value) else {
            return bad_line(line_no, line);
        };
        sum = next;
        if !any {
            low = value;
            high = value;
            max_at = start;
            max_len = space;
            any = true;
        } else {
            if value < low {
                low = value;
            }
            if value > high {
                high = value;
                max_at = start;
                max_len = space;
            }
        }
        count += 1;
        if end == data.len() {
            break;
        }
        start = end + 1;
        line_no += 1;
        if start == data.len() {
            break;
        }
    }

    let mean = sum / count;
    let mut out = io::stdout().lock();
    write!(out, "count {count}\nmean {mean}\nmin {low}\nmax {high}\nname ").ok();
    out.write_all(&data[max_at..max_at + max_len]).ok();
    out.write_all(b"\n").ok();
    ExitCode::from(0)
}
