// Probe 02 shelf. Contract: probes/02-shelf/task.md.
const std = @import("std");

const max_bytes: usize = 1_048_576;

fn fail(message: []const u8) noreturn {
    var buffer: [256]u8 = undefined;
    var writer = std.fs.File.stderr().writer(&buffer);
    const out = &writer.interface;
    out.writeAll(message) catch std.process.exit(1);
    out.writeAll("\n") catch std.process.exit(1);
    out.flush() catch std.process.exit(1);
    std.process.exit(1);
}

fn fail_open(path: []const u8) noreturn {
    var buffer: [4096]u8 = undefined;
    var writer = std.fs.File.stderr().writer(&buffer);
    const out = &writer.interface;
    out.writeAll("cannot open ") catch std.process.exit(1);
    out.writeAll(path) catch std.process.exit(1);
    out.writeAll("\n") catch std.process.exit(1);
    out.flush() catch std.process.exit(1);
    std.process.exit(1);
}

fn fail_line(line_no: i64, line: []const u8) noreturn {
    var buffer: [4096]u8 = undefined;
    var writer = std.fs.File.stderr().writer(&buffer);
    const out = &writer.interface;
    out.print("bad line {d}: ", .{line_no}) catch std.process.exit(1);
    out.writeAll(line) catch std.process.exit(1);
    out.writeAll("\n") catch std.process.exit(1);
    out.flush() catch std.process.exit(1);
    std.process.exit(1);
}

fn name_byte(byte: u8) bool {
    return (byte >= 'A' and byte <= 'Z') or (byte >= 'a' and byte <= 'z') or
        (byte >= '0' and byte <= '9') or byte == '_';
}

fn parse_i64(text: []const u8) ?i64 {
    if (text.len == 0 or std.mem.eql(u8, text, "+") or std.mem.eql(u8, text, "-")) {
        return null;
    }
    const body = if (text[0] == '+' or text[0] == '-') text[1..] else text;
    if (body.len == 0) return null;
    for (body) |byte| {
        if (byte < '0' or byte > '9') return null;
    }
    return std.fmt.parseInt(i64, text, 10) catch null;
}

const Row = struct { name: []const u8, qty: i64, price: i64 };

fn parse_row(line: []const u8) ?Row {
    const first = std.mem.indexOfScalar(u8, line, ' ') orelse return null;
    if (first == 0) return null;
    const second_rel = std.mem.indexOfScalar(u8, line[first + 1 ..], ' ') orelse return null;
    const second = first + 1 + second_rel;
    if (second == first + 1 or second + 1 == line.len) return null;
    if (std.mem.indexOfScalar(u8, line[second + 1 ..], ' ') != null) return null;
    const name = line[0..first];
    for (name) |byte| {
        if (!name_byte(byte)) return null;
    }
    const qty = parse_i64(line[first + 1 .. second]) orelse return null;
    const price = parse_i64(line[second + 1 ..]) orelse return null;
    return .{ .name = name, .qty = qty, .price = price };
}

pub fn main() !void {
    var arg_buffer: [8192]u8 = undefined;
    var arg_fixed = std.heap.FixedBufferAllocator.init(&arg_buffer);
    const args = try std.process.argsAlloc(arg_fixed.allocator());
    if (args.len != 2) fail("usage: shelf <file>");
    const path = args[1];

    const file = std.fs.cwd().openFile(path, .{}) catch fail_open(path);
    defer file.close();
    const stat = file.stat() catch fail_open(path);
    if (stat.size > max_bytes) fail("file too large");
    if (stat.size == 0) fail("empty file");
    const data = file.readToEndAlloc(std.heap.page_allocator, max_bytes) catch |err| switch (err) {
        error.FileTooBig => fail("file too large"),
        else => fail_open(path),
    };
    defer std.heap.page_allocator.free(data);

    var count: i64 = 0;
    var pieces: i64 = 0;
    var worth: i64 = 0;
    var high: i64 = 0;
    var item: []const u8 = "";
    var any = false;
    var line_no: i64 = 1;
    var start: usize = 0;
    while (start < data.len) {
        var end = start;
        while (end < data.len and data[end] != '\n') : (end += 1) {}
        var line = data[start..end];
        if (line.len > 0 and line[line.len - 1] == '\r') line = line[0 .. line.len - 1];
        const row = parse_row(line) orelse fail_line(line_no, line);
        const line_value = std.math.mul(i64, row.qty, row.price) catch fail_line(line_no, line);
        pieces = std.math.add(i64, pieces, row.qty) catch fail_line(line_no, line);
        worth = std.math.add(i64, worth, line_value) catch fail_line(line_no, line);
        if (!any) {
            high = line_value;
            item = row.name;
            any = true;
        } else if (line_value > high) {
            high = line_value;
            item = row.name;
        }
        count += 1;
        if (end == data.len) break;
        start = end + 1;
        line_no += 1;
        if (start == data.len) break;
    }

    var out_buffer: [256]u8 = undefined;
    var out_writer = std.fs.File.stdout().writer(&out_buffer);
    const out = &out_writer.interface;
    try out.print("count {d}\npieces {d}\nvalue {d}\nitem ", .{ count, pieces, worth });
    try out.writeAll(item);
    try out.writeAll("\n");
    try out.flush();
}
