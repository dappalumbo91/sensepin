// Probe 01 grades. Contract: probes/01-grades/task.md.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const maxBytes = 1048576

func die(message string) {
	fmt.Fprintln(os.Stderr, message)
	os.Exit(1)
}

func nameByte(byte byte) bool {
	return (byte >= 'A' && byte <= 'Z') || (byte >= 'a' && byte <= 'z') ||
		(byte >= '0' && byte <= '9') || byte == '_'
}

func parseI64(text string) (int64, bool) {
	if text == "" || text == "+" || text == "-" {
		return 0, false
	}
	body := text
	if text[0] == '+' || text[0] == '-' {
		body = text[1:]
	}
	if body == "" {
		return 0, false
	}
	for i := 0; i < len(body); i++ {
		if body[i] < '0' || body[i] > '9' {
			return 0, false
		}
	}
	value, err := strconv.ParseInt(text, 10, 64)
	if err != nil {
		return 0, false
	}
	return value, true
}

func parseGrade(raw []byte) (string, int64, bool) {
	space := -1
	for i := 0; i < len(raw); i++ {
		if raw[i] == ' ' {
			if space >= 0 {
				return "", 0, false
			}
			space = i
		}
	}
	if space <= 0 {
		return "", 0, false
	}
	name := raw[:space]
	for i := 0; i < len(name); i++ {
		if !nameByte(name[i]) {
			return "", 0, false
		}
	}
	value, ok := parseI64(string(raw[space+1:]))
	if !ok {
		return "", 0, false
	}
	return string(name), value, true
}

func add(sum int64, value int64) (int64, bool) {
	if value > 0 && sum > (1<<63-1)-value {
		return 0, true
	}
	if value < 0 && sum < (-1<<63)-value {
		return 0, true
	}
	return sum + value, false
}

func main() {
	if len(os.Args) != 2 {
		die("usage: grades <file>")
	}
	path := os.Args[1]
	info, err := os.Stat(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot open %s\n", path)
		os.Exit(1)
	}
	if info.Size() > maxBytes {
		die("file too large")
	}
	if info.Size() == 0 {
		die("empty file")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot open %s\n", path)
		os.Exit(1)
	}

	var count int64
	var sum int64
	var low int64
	var high int64
	var maxName string
	any := false
	lineNo := int64(1)
	start := 0
	for start < len(data) {
		end := start
		for end < len(data) && data[end] != '\n' {
			end++
		}
		raw := data[start:end]
		if len(raw) > 0 && raw[len(raw)-1] == '\r' {
			raw = raw[:len(raw)-1]
		}
		name, value, ok := parseGrade(raw)
		if !ok {
			fmt.Fprintf(os.Stderr, "bad line %d: %s\n", lineNo, raw)
			os.Exit(1)
		}
		next, overflow := add(sum, value)
		if overflow {
			fmt.Fprintf(os.Stderr, "bad line %d: %s\n", lineNo, raw)
			os.Exit(1)
		}
		sum = next
		if !any {
			low = value
			high = value
			maxName = name
			any = true
		} else {
			if value < low {
				low = value
			}
			if value > high {
				high = value
				maxName = name
			}
		}
		count++
		if end == len(data) {
			break
		}
		start = end + 1
		lineNo++
		if start == len(data) {
			break
		}
	}

	mean := sum / count
	fmt.Printf("count %d\nmean %d\nmin %d\nmax %d\nname %s\n", count, mean, low, high, maxName)
}
