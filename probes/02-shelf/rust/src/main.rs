//! Probe 02 shelf. Contract: probes/02-shelf/task.md.

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

fn parse_row(line: &[u8]) -> Option<(usize, i64, i64)> {
    let mut spaces = line.iter().enumerate().filter(|(_, byte)| **byte == b' ');
    let (first, _) = spaces.next()?;
    let (second, _) = spaces.next()?;
    if spaces.next().is_some() || first == 0 || second == first + 1 || second + 1 == line.len() {
        return None;
    }
    if !line[..first].iter().copied().all(name_byte) {
        return None;
    }
    let qty_text = std::str::from_utf8(&line[first + 1..second]).ok()?;
    let price_text = std::str::from_utf8(&line[second + 1..]).ok()?;
    let qty = parse_i64(qty_text)?;
    let price = parse_i64(price_text)?;
    Some((first, qty, price))
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
        return emit("usage: shelf <file>");
    };
    if args.next().is_some() {
        return emit("usage: shelf <file>");
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
    let mut pieces: i64 = 0;
    let mut worth: i64 = 0;
    let mut high: i64 = 0;
    let mut item_at = 0usize;
    let mut item_len = 0usize;
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
        let Some((name_len, qty, price)) = parse_row(line) else {
            return bad_line(line_no, line);
        };
        let Some(line_value) = qty.checked_mul(price) else {
            return bad_line(line_no, line);
        };
        let Some(next_pieces) = pieces.checked_add(qty) else {
            return bad_line(line_no, line);
        };
        let Some(next_worth) = worth.checked_add(line_value) else {
            return bad_line(line_no, line);
        };
        pieces = next_pieces;
        worth = next_worth;
        if !any {
            high = line_value;
            item_at = start;
            item_len = name_len;
            any = true;
        } else if line_value > high {
            high = line_value;
            item_at = start;
            item_len = name_len;
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

    let mut out = io::stdout().lock();
    write!(out, "count {count}\npieces {pieces}\nvalue {worth}\nitem ").ok();
    out.write_all(&data[item_at..item_at + item_len]).ok();
    out.write_all(b"\n").ok();
    ExitCode::from(0)
}
