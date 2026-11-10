// Probe 02 shelf. Contract: probes/02-shelf/task.md.
package main

import (
	"fmt"
	"math"
	"os"
	"strconv"
)

const maxBytes = 1048576

func die(message string) {
	fmt.Fprintln(os.Stderr, message)
	os.Exit(1)
}

func dieLine(lineNo int64, raw []byte) {
	fmt.Fprintf(os.Stderr, "bad line %d: %s\n", lineNo, raw)
	os.Exit(1)
}

func nameByte(b byte) bool {
	return (b >= 'A' && b <= 'Z') || (b >= 'a' && b <= 'z') ||
		(b >= '0' && b <= '9') || b == '_'
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

func add(sum int64, value int64) (int64, bool) {
	if value > 0 && sum > math.MaxInt64-value {
		return 0, false
	}
	if value < 0 && sum < math.MinInt64-value {
		return 0, false
	}
	return sum + value, true
}

func mul(a int64, b int64) (int64, bool) {
	if a == 0 || b == 0 {
		return 0, true
	}
	if a == math.MinInt64 {
		if b == 1 {
			return a, true
		}
		return 0, false
	}
	if b == math.MinInt64 {
		if a == 1 {
			return b, true
		}
		return 0, false
	}
	aa := a
	if aa < 0 {
		aa = -aa
	}
	bb := b
	if bb < 0 {
		bb = -bb
	}
	if aa > math.MaxInt64/bb {
		return 0, false
	}
	return a * b, true
}

func parseRow(raw []byte) (string, int64, int64, bool) {
	spaces := []int{}
	for i := 0; i < len(raw); i++ {
		if raw[i] == ' ' {
			spaces = append(spaces, i)
		}
	}
	if len(spaces) != 2 || spaces[0] == 0 || spaces[1] == spaces[0]+1 || spaces[1] == len(raw)-1 {
		return "", 0, 0, false
	}
	name := raw[:spaces[0]]
	for i := 0; i < len(name); i++ {
		if !nameByte(name[i]) {
			return "", 0, 0, false
		}
	}
	qty, okQty := parseI64(string(raw[spaces[0]+1 : spaces[1]]))
	price, okPrice := parseI64(string(raw[spaces[1]+1:]))
	if !okQty || !okPrice {
		return "", 0, 0, false
	}
	return string(name), qty, price, true
}

func main() {
	if len(os.Args) != 2 {
		die("usage: shelf <file>")
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
	var pieces int64
	var worth int64
	var high int64
	var item string
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
		name, qty, price, ok := parseRow(raw)
		if !ok {
			dieLine(lineNo, raw)
		}
		lineValue, okMul := mul(qty, price)
		nextPieces, okPieces := add(pieces, qty)
		nextWorth, okWorth := add(worth, lineValue)
		if !okMul || !okPieces || !okWorth {
			dieLine(lineNo, raw)
		}
		pieces = nextPieces
		worth = nextWorth
		if !any {
			high = lineValue
			item = name
			any = true
		} else if lineValue > high {
			high = lineValue
			item = name
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

	fmt.Printf("count %d\npieces %d\nvalue %d\nitem %s\n", count, pieces, worth, item)
}
