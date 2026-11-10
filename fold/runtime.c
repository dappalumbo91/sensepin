/* Sensepin gauge runtime. Behavior is fold/SPEC.md. */
#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#if defined(__clang__) || defined(__GNUC__)
#pragma GCC diagnostic ignored "-Wunused-function"
#endif

typedef struct FoldBytes {
    const uint8_t *p;
    size_t n;
} FoldBytes;

typedef struct FoldValue {
    int failed;
    FoldBytes reason;
    FoldBytes bytes;
    int64_t i64;
} FoldValue;

typedef struct FoldLine {
    FoldBytes text;
    int64_t n;
} FoldLine;

typedef struct FoldLines {
    FoldLine *items;
    size_t count;
} FoldLines;

typedef struct FoldChunk {
    struct FoldChunk *prev;
    size_t used;
    size_t cap;
    uint8_t data[];
} FoldChunk;

static FoldChunk *fold_chunk;
static int fold_argc_value;
static char **fold_argv_value;

static void fold_oom(void) {
    fputs("out of memory\n", stderr);
    exit(1);
}

static void *fold_alloc(size_t n) {
    if (fold_chunk != NULL && n <= fold_chunk->cap - fold_chunk->used) {
        void *out = fold_chunk->data + fold_chunk->used;
        fold_chunk->used += n;
        return out;
    }
    size_t cap = 4096;
    if (n > cap) {
        cap = n;
    }
    if (cap > SIZE_MAX - sizeof(FoldChunk)) {
        fold_oom();
    }
    FoldChunk *next = (FoldChunk *)malloc(sizeof(FoldChunk) + cap);
    if (next == NULL) {
        fold_oom();
    }
    next->prev = fold_chunk;
    next->used = 0;
    next->cap = cap;
    fold_chunk = next;
    fold_chunk->used = n;
    return fold_chunk->data;
}

static FoldBytes fold_bytes_empty(void) {
    FoldBytes b;
    b.p = (const uint8_t *)"";
    b.n = 0;
    return b;
}

static FoldBytes fold_bytes_view(const uint8_t *p, size_t n) {
    FoldBytes b;
    b.p = p;
    b.n = n;
    return b;
}

static FoldBytes fold_cat(FoldBytes a, FoldBytes b) {
    if (a.n > SIZE_MAX - b.n) {
        fold_oom();
    }
    uint8_t *p = (uint8_t *)fold_alloc(a.n + b.n == 0 ? 1 : a.n + b.n);
    if (a.n) {
        memcpy(p, a.p, a.n);
    }
    if (b.n) {
        memcpy(p + a.n, b.p, b.n);
    }
    return fold_bytes_view(p, a.n + b.n);
}

static FoldBytes fold_dec(int64_t value) {
    char buf[32];
    int n = snprintf(buf, sizeof buf, "%lld", (long long)value);
    if (n < 0 || (size_t)n >= sizeof buf) {
        fold_oom();
    }
    uint8_t *p = (uint8_t *)fold_alloc((size_t)n == 0 ? 1 : (size_t)n);
    memcpy(p, buf, (size_t)n);
    return fold_bytes_view(p, (size_t)n);
}

#if defined(__clang__) || defined(__GNUC__)
__attribute__((noreturn))
#endif
static void fold_fail(FoldBytes message) {
    if (message.n) {
        fwrite(message.p, 1, message.n, stderr);
    }
    fputc('\n', stderr);
    exit(1);
}

static void fold_write(FoldBytes message) {
    if (message.n) {
        fwrite(message.p, 1, message.n, stdout);
    }
}

#define FOLD_CALL_DEPTH 256

static int fold_depth;

static void fold_enter(void) {
    if (fold_depth >= FOLD_CALL_DEPTH) {
        fputs("call depth\n", stderr);
        exit(1);
    }
    fold_depth++;
}

static void fold_leave(void) {
    if (fold_depth > 0) {
        fold_depth--;
    }
}

static void fold_init(int argc, char **argv) {
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);
#endif
    fold_argc_value = argc;
    fold_argv_value = argv;
}

static int64_t fold_argc(void) {
    return fold_argc_value;
}

static FoldValue fold_arg(int64_t index) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (index < 0 || index >= fold_argc_value) {
        out.failed = 1;
        return out;
    }
    out.bytes = fold_bytes_view((const uint8_t *)fold_argv_value[index], strlen(fold_argv_value[index]));
    return out;
}

static FoldValue fold_i64(FoldBytes text) {
    FoldValue out;
    size_t i = 0;
    int neg = 0;
    uint64_t acc = 0;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (text.n == 0) {
        out.failed = 1;
        return out;
    }
    if (text.p[0] == '+' || text.p[0] == '-') {
        neg = text.p[0] == '-';
        i = 1;
        if (i == text.n) {
            out.failed = 1;
            return out;
        }
    }
    for (; i < text.n; i++) {
        unsigned digit;
        if (text.p[i] < '0' || text.p[i] > '9') {
            out.failed = 1;
            return out;
        }
        digit = (unsigned)(text.p[i] - '0');
        if (acc > UINT64_MAX / 10 || (acc == UINT64_MAX / 10 && digit > UINT64_MAX % 10)) {
            out.failed = 1;
            return out;
        }
        acc = acc * 10u + digit;
    }
    if (!neg) {
        if (acc > (uint64_t)INT64_MAX) {
            out.failed = 1;
            return out;
        }
        out.i64 = (int64_t)acc;
        return out;
    }
    if (acc > (uint64_t)INT64_MAX + 1u) {
        out.failed = 1;
        return out;
    }
    if (acc == (uint64_t)INT64_MAX + 1u) {
        out.i64 = INT64_MIN;
        return out;
    }
    out.i64 = -(int64_t)acc;
    return out;
}

static FoldValue fold_add(int64_t a, int64_t b) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (b > 0 && a > INT64_MAX - b) {
        out.failed = 1;
        return out;
    }
    if (b < 0 && a < INT64_MIN - b) {
        out.failed = 1;
        return out;
    }
    out.i64 = a + b;
    return out;
}

static FoldValue fold_sub(int64_t a, int64_t b) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (b == INT64_MIN) {
        out.failed = 1;
        return out;
    }
    return fold_add(a, -b);
}

static FoldValue fold_neg(int64_t value) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (value == INT64_MIN) {
        out.failed = 1;
        return out;
    }
    out.i64 = -value;
    return out;
}

static FoldValue fold_open(FoldBytes path, int64_t limit, FoldBytes missing, FoldBytes empty, FoldBytes large) {
    FoldValue out;
    char *owned = NULL;
    FILE *file = NULL;
    size_t size = 0;
    uint8_t *buf;
    size_t got = 0;
    memset(&out, 0, sizeof out);
    if (limit < 0) {
        out.failed = 1;
        out.reason = large;
        return out;
    }
    if (path.n == SIZE_MAX) {
        fold_oom();
    }
    owned = (char *)malloc(path.n + 1);
    if (owned == NULL) {
        fold_oom();
    }
    if (path.n) {
        memcpy(owned, path.p, path.n);
    }
    owned[path.n] = '\0';
    if (strlen(owned) != path.n) {
        free(owned);
        out.failed = 1;
        out.reason = fold_cat(missing, path);
        return out;
    }
    file = fopen(owned, "rb");
    free(owned);
    if (file == NULL) {
        out.failed = 1;
        out.reason = fold_cat(missing, path);
        return out;
    }
    {
#ifdef _WIN32
        struct __stat64 st;
        int regular = _fstat64(_fileno(file), &st) == 0 && (st.st_mode & _S_IFMT) == _S_IFREG;
#else
        struct stat st;
        int regular = fstat(fileno(file), &st) == 0 && S_ISREG(st.st_mode);
#endif
        if (!regular) {
            fclose(file);
            out.failed = 1;
            out.reason = fold_cat(missing, path);
            return out;
        }
    }
    {
#ifdef _WIN32
        int seek_ok = _fseeki64(file, 0, SEEK_END) == 0;
        __int64 wide = seek_ok ? _ftelli64(file) : -1;
        seek_ok = seek_ok && wide >= 0 && _fseeki64(file, 0, SEEK_SET) == 0;
#else
        int seek_ok = fseeko(file, 0, SEEK_END) == 0;
        off_t wide = seek_ok ? ftello(file) : (off_t)-1;
        seek_ok = seek_ok && wide >= 0 && fseeko(file, 0, SEEK_SET) == 0;
#endif
        if (!seek_ok) {
            fclose(file);
            out.failed = 1;
            out.reason = fold_cat(missing, path);
            return out;
        }
        if ((unsigned long long)wide > (unsigned long long)limit || (uint64_t)wide > (uint64_t)SIZE_MAX) {
            fclose(file);
            out.failed = 1;
            out.reason = large;
            return out;
        }
        size = (size_t)wide;
    }
    if (size == 0) {
        fclose(file);
        out.failed = 1;
        out.reason = empty;
        return out;
    }
    buf = (uint8_t *)malloc((size_t)size);
    if (buf == NULL) {
        fclose(file);
        fold_oom();
    }
    while (got < (size_t)size) {
        size_t n = fread(buf + got, 1, (size_t)size - got, file);
        if (n == 0) {
            free(buf);
            fclose(file);
            out.failed = 1;
            out.reason = fold_cat(missing, path);
            return out;
        }
        got += n;
    }
    fclose(file);
    out.bytes = fold_bytes_view(buf, (size_t)size);
    return out;
}

static void fold_lines(FoldBytes text, FoldLines *out) {
    size_t count = 0;
    size_t i = 0;
    size_t at = 0;
    while (i < text.n) {
        size_t end = i;
        while (end < text.n && text.p[end] != '\n') {
            end++;
        }
        count++;
        if (end == text.n) {
            break;
        }
        i = end + 1;
        if (i == text.n) {
            break;
        }
    }
    out->count = count;
    out->items = NULL;
    if (count == 0) {
        return;
    }
    if (count > (size_t)INT64_MAX || count > SIZE_MAX / sizeof(FoldLine)) {
        fold_oom();
    }
    out->items = (FoldLine *)malloc(count * sizeof(FoldLine));
    if (out->items == NULL) {
        fold_oom();
    }
    i = 0;
    while (i < text.n) {
        size_t end = i;
        size_t stop;
        FoldLine line;
        while (end < text.n && text.p[end] != '\n') {
            end++;
        }
        stop = end;
        if (stop > i && text.p[stop - 1] == '\r') {
            stop--;
        }
        if (at >= count) {
            free(out->items);
            out->items = NULL;
            fold_oom();
        }
        line.text = fold_bytes_view(text.p + i, stop - i);
        line.n = (int64_t)at + 1;
        out->items[at++] = line;
        if (end == text.n) {
            break;
        }
        i = end + 1;
        if (i == text.n) {
            break;
        }
    }
    if (at != count) {
        free(out->items);
        out->items = NULL;
        fold_oom();
    }
}

/*FOLD_PROGRAM*/

#ifndef FOLD_NO_ENTRY
int main(int argc, char **argv) {
    fold_init(argc, argv);
    return fold_main();
}
#endif
