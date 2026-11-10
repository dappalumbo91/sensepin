//! Probe 00 tally. Contract: probes/00-tally/task.md.

use std::env;
use std::fs;
use std::io::{self, Write};
use std::process::ExitCode;

const MAX_BYTES: usize = 1_048_576;

fn emit(message: &str) -> ExitCode {
    eprintln!("{message}");
    ExitCode::from(1)
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

fn main() -> ExitCode {
    let mut args = env::args();
    let _program = args.next();
    let Some(path) = args.next() else {
        return emit("usage: tally <file>");
    };
    if args.next().is_some() {
        return emit("usage: tally <file>");
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
    let mut any = false;
    let mut line_no: i64 = 1;
    let mut start = 0usize;
    while start < data.len() {
        let mut end = start;
        while end < data.len() && data[end] != b'\n' {
            end += 1;
        }
        let mut line = &data[start..end];
        if line.last() == Some(&b'\r') {
            line = &line[..line.len() - 1];
        }
        let text = std::str::from_utf8(line).ok();
        let Some(value) = text.and_then(parse_i64) else {
            let mut err = io::stderr().lock();
            write!(err, "bad line {line_no}: ").ok();
            err.write_all(line).ok();
            writeln!(err).ok();
            return ExitCode::from(1);
        };
        let Some(next) = sum.checked_add(value) else {
            let mut err = io::stderr().lock();
            write!(err, "bad line {line_no}: ").ok();
            err.write_all(line).ok();
            writeln!(err).ok();
            return ExitCode::from(1);
        };
        sum = next;
        if !any {
            low = value;
            high = value;
            any = true;
        } else {
            if value < low {
                low = value;
            }
            if value > high {
                high = value;
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

    print!("count {count}\nsum {sum}\nmin {low}\nmax {high}\n");
    ExitCode::from(0)
}
