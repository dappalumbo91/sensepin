/* Sensepin gauge runtime. Behavior is fold/SPEC.md. */
#define _CRT_SECURE_NO_WARNINGS
#include "runtime.h"
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

FOLD_API FoldBytes fold_bytes_empty(void) {
    FoldBytes b;
    b.p = (const uint8_t *)"";
    b.n = 0;
    return b;
}

FOLD_API FoldBytes fold_bytes_view(const uint8_t *p, size_t n) {
    FoldBytes b;
    b.p = p;
    b.n = n;
    return b;
}

FOLD_API FoldBytes fold_cat(FoldBytes a, FoldBytes b) {
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

FOLD_API FoldBytes fold_dec(int64_t value) {
    char buf[32];
    int n = snprintf(buf, sizeof buf, "%lld", (long long)value);
    if (n < 0 || (size_t)n >= sizeof buf) {
        fold_oom();
    }
    uint8_t *p = (uint8_t *)fold_alloc((size_t)n == 0 ? 1 : (size_t)n);
    memcpy(p, buf, (size_t)n);
    return fold_bytes_view(p, (size_t)n);
}

static int fold_f64_finite(double value) {
    uint64_t bits = 0;
    memcpy(&bits, &value, sizeof bits);
    return (bits & 0x7ff0000000000000ull) != 0x7ff0000000000000ull;
}

FOLD_API FoldBytes fold_dec_f64(double value) {
    char buf[64];
    int n;
    if (value == 0) {
        value = 0;
    }
    n = snprintf(buf, sizeof buf, "%.17g", value);
    if (n < 0 || (size_t)n >= sizeof buf) {
        fold_oom();
    }
    if (strchr(buf, '.') == NULL && strchr(buf, 'e') == NULL && strchr(buf, 'E') == NULL) {
        if ((size_t)n + 2 >= sizeof buf) {
            fold_oom();
        }
        buf[n++] = '.';
        buf[n++] = '0';
        buf[n] = '\0';
    }
    {
        uint8_t *p = (uint8_t *)fold_alloc((size_t)n == 0 ? 1 : (size_t)n);
        memcpy(p, buf, (size_t)n);
        return fold_bytes_view(p, (size_t)n);
    }
}

FOLD_API double fold_f64_bits(uint64_t bits) {
    double value = 0;
    memcpy(&value, &bits, sizeof value);
    return value;
}

FOLD_API const void *fold_box(const void *p, size_t n) {
    void *out = fold_alloc(n == 0 ? 1 : n);
    if (n != 0 && p != NULL) {
        memcpy(out, p, n);
    }
    return out;
}

#if defined(__clang__) || defined(__GNUC__)
__attribute__((noreturn))
#endif
FOLD_API void fold_fail(FoldBytes message) {
    if (message.n) {
        fwrite(message.p, 1, message.n, stderr);
    }
    fputc('\n', stderr);
    exit(1);
}

FOLD_API void fold_write(FoldBytes message) {
    if (message.n) {
        fwrite(message.p, 1, message.n, stdout);
    }
}

#define FOLD_CALL_DEPTH 256

static int fold_depth;

FOLD_API void fold_enter(void) {
    if (fold_depth >= FOLD_CALL_DEPTH) {
        fputs("call depth\n", stderr);
        exit(1);
    }
    fold_depth++;
}

FOLD_API void fold_leave(void) {
    if (fold_depth > 0) {
        fold_depth--;
    }
}

FOLD_API void fold_init(int argc, char **argv) {
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);
#endif
    fold_argc_value = argc;
    fold_argv_value = argv;
}

FOLD_API int64_t fold_argc(void) {
    return fold_argc_value;
}

FOLD_API FoldValue fold_arg(int64_t index) {
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

FOLD_API FoldValue fold_i64(FoldBytes text) {
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

FOLD_API FoldValue fold_add(int64_t a, int64_t b) {
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

FOLD_API FoldValue fold_sub(int64_t a, int64_t b) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (b == INT64_MIN) {
        out.failed = 1;
        return out;
    }
    return fold_add(a, -b);
}

FOLD_API FoldValue fold_div(int64_t a, int64_t b) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (b == 0 || (a == INT64_MIN && b == -1)) {
        out.failed = 1;
        return out;
    }
    out.i64 = a / b;
    return out;
}

FOLD_API FoldValue fold_mul(int64_t a, int64_t b) {
    FoldValue out;
    int64_t aa;
    int64_t bb;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (a == 0 || b == 0) {
        out.i64 = 0;
        return out;
    }
    if (a == INT64_MIN) {
        out.failed = b != 1;
        out.i64 = b == 1 ? a : 0;
        return out;
    }
    if (b == INT64_MIN) {
        out.failed = a != 1;
        out.i64 = a == 1 ? b : 0;
        return out;
    }
    aa = a < 0 ? -a : a;
    bb = b < 0 ? -b : b;
    if (aa > INT64_MAX / bb) {
        out.failed = 1;
        return out;
    }
    out.i64 = a * b;
    return out;
}

static FoldValue fold_f64_value(double value) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (!fold_f64_finite(value)) {
        out.failed = 1;
        return out;
    }
    out.f64 = value;
    return out;
}

FOLD_API FoldValue fold_fadd(double a, double b) {
    return fold_f64_value(a + b);
}

FOLD_API FoldValue fold_fsub(double a, double b) {
    return fold_f64_value(a - b);
}

FOLD_API FoldValue fold_fmul(double a, double b) {
    return fold_f64_value(a * b);
}

FOLD_API FoldValue fold_fdiv(double a, double b) {
    return fold_f64_value(a / b);
}

FOLD_API FoldValue fold_fneg(double value) {
    return fold_f64_value(-value);
}

FOLD_API FoldValue fold_f64_from_i64(int64_t value) {
    return fold_f64_value((double)value);
}

FOLD_API FoldValue fold_i64_from_f64(double value) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (!fold_f64_finite(value) || value >= 9223372036854775808.0 || value < -9223372036854775808.0) {
        out.failed = 1;
        return out;
    }
    out.i64 = (int64_t)value;
    return out;
}

FOLD_API FoldValue fold_neg(int64_t value) {
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

FOLD_API FoldValue fold_open(FoldBytes path, int64_t limit, FoldBytes missing, FoldBytes empty, FoldBytes large) {
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

static int fold_find(FoldBytes text, FoldBytes sep, size_t *at) {
    size_t i;
    if (sep.n == 0 || sep.n > text.n) {
        return 0;
    }
    for (i = 0; i <= text.n - sep.n; i++) {
        if (memcmp(text.p + i, sep.p, sep.n) == 0) {
            *at = i;
            return 1;
        }
    }
    return 0;
}

FOLD_API FoldValue fold_byte(int64_t value) {
    FoldValue out;
    uint8_t *p;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (value < 0 || value > 255) {
        out.failed = 1;
        return out;
    }
    p = (uint8_t *)fold_alloc(1);
    p[0] = (uint8_t)value;
    out.bytes = fold_bytes_view(p, 1);
    return out;
}

FOLD_API FoldValue fold_set_byte(FoldBytes text, int64_t index, int64_t value) {
    FoldValue out;
    uint8_t *p;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (value < 0 || value > 255 || index < 0 || (uint64_t)index >= text.n) {
        out.failed = 1;
        return out;
    }
    p = (uint8_t *)fold_alloc(text.n);
    if (text.n) {
        memcpy(p, text.p, text.n);
    }
    p[index] = (uint8_t)value;
    out.bytes = fold_bytes_view(p, text.n);
    return out;
}

FOLD_API FoldValue fold_save(FoldBytes path, FoldBytes data) {
    FoldValue out;
    char *owned;
    FILE *file;
    size_t put = 0;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
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
        return out;
    }
    file = fopen(owned, "wb");
    free(owned);
    if (file == NULL) {
        out.failed = 1;
        return out;
    }
    while (put < data.n) {
        size_t n = fwrite(data.p + put, 1, data.n - put, file);
        if (n == 0) {
            fclose(file);
            out.failed = 1;
            return out;
        }
        put += n;
    }
    if (fclose(file) != 0) {
        out.failed = 1;
        return out;
    }
    out.i64 = (int64_t)data.n;
    return out;
}

FOLD_API FoldValue fold_len(FoldBytes text) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (text.n > (size_t)INT64_MAX) {
        out.failed = 1;
        return out;
    }
    out.i64 = (int64_t)text.n;
    return out;
}

FOLD_API FoldValue fold_before(FoldBytes text, FoldBytes sep) {
    FoldValue out;
    size_t at = 0;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (!fold_find(text, sep, &at)) {
        out.failed = 1;
        return out;
    }
    out.bytes = fold_bytes_view(text.p, at);
    return out;
}

FOLD_API FoldValue fold_after(FoldBytes text, FoldBytes sep) {
    FoldValue out;
    size_t at = 0;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (!fold_find(text, sep, &at)) {
        out.failed = 1;
        return out;
    }
    out.bytes = fold_bytes_view(text.p + at + sep.n, text.n - at - sep.n);
    return out;
}

FOLD_API FoldValue fold_holds(FoldBytes text, FoldBytes sep) {
    FoldValue out;
    size_t count = 0;
    size_t i = 0;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (sep.n == 0) {
        out.failed = 1;
        return out;
    }
    while (i <= text.n && sep.n <= text.n - i) {
        if (memcmp(text.p + i, sep.p, sep.n) == 0) {
            count++;
            i += sep.n;
        } else {
            i++;
        }
    }
    if (count > (size_t)INT64_MAX) {
        out.failed = 1;
        return out;
    }
    out.i64 = (int64_t)count;
    return out;
}

FOLD_API FoldList fold_list_empty(size_t stride) {
    FoldList xs;
    xs.items = NULL;
    xs.count = 0;
    xs.stride = stride;
    return xs;
}

FOLD_API uint8_t *fold_list_alloc(size_t count, size_t stride) {
    if (stride == 0 || count > SIZE_MAX / stride) {
        fold_oom();
    }
    return (uint8_t *)fold_alloc(count * stride);
}

FOLD_API FoldList fold_list_push(FoldList xs, const void *elem, size_t stride) {
    size_t n;
    uint8_t *p;
    if (stride == 0 || xs.count == SIZE_MAX || xs.count + 1 > SIZE_MAX / stride) {
        fold_oom();
    }
    n = xs.count + 1;
    p = (uint8_t *)fold_alloc(n * stride);
    if (xs.count != 0 && xs.items != NULL) {
        memcpy(p, xs.items, xs.count * stride);
    }
    if (elem != NULL) {
        memcpy(p + xs.count * stride, elem, stride);
    }
    xs.items = p;
    xs.count = n;
    xs.stride = stride;
    return xs;
}

FOLD_API FoldValue fold_list_len(FoldList xs) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (xs.count > (size_t)INT64_MAX) {
        out.failed = 1;
        return out;
    }
    out.i64 = (int64_t)xs.count;
    return out;
}

FOLD_API int fold_list_index(FoldList xs, int64_t index) {
    if (index < 0) {
        return 0;
    }
    if ((uint64_t)index >= (uint64_t)xs.count) {
        return 0;
    }
    return 1;
}

static uint8_t *fold_map_block(size_t bytes) {
    size_t padded;
    if (bytes == 0) {
        return NULL;
    }
    if (bytes > SIZE_MAX - 7) {
        fold_oom();
    }
    padded = (bytes + 7u) & ~(size_t)7u;
    return (uint8_t *)fold_alloc(padded);
}

static int fold_map_same(const uint8_t *stored, const void *key, size_t stride, int kind) {
    if (kind == FOLD_KEY_F64) {
        double left;
        double right;
        memcpy(&left, stored, sizeof left);
        memcpy(&right, key, sizeof right);
        return left == right;
    }
    if (kind == FOLD_KEY_BYTES) {
        FoldBytes left;
        FoldBytes right;
        memcpy(&left, stored, sizeof left);
        memcpy(&right, key, sizeof right);
        if (left.n != right.n) {
            return 0;
        }
        if (left.n == 0) {
            return 1;
        }
        if (left.p == NULL || right.p == NULL) {
            return left.p == right.p;
        }
        return memcmp(left.p, right.p, left.n) == 0;
    }
    if (stride == 0 || stored == NULL || key == NULL) {
        return 0;
    }
    return memcmp(stored, key, stride) == 0;
}

FOLD_API FoldMap fold_map_empty(size_t key_stride, size_t val_stride) {
    FoldMap out;
    out.keys = NULL;
    out.vals = NULL;
    out.count = 0;
    out.key_stride = key_stride;
    out.val_stride = val_stride;
    return out;
}

FOLD_API int fold_map_find(FoldMap src, const void *key, int kind, size_t *index) {
    size_t i;
    if (key == NULL || src.keys == NULL || src.key_stride == 0) {
        return 0;
    }
    for (i = 0; i < src.count; i++) {
        if (fold_map_same(src.keys + i * src.key_stride, key, src.key_stride, kind)) {
            if (index != NULL) {
                *index = i;
            }
            return 1;
        }
    }
    return 0;
}

FOLD_API int64_t fold_map_has(FoldMap src, const void *key, int kind) {
    return fold_map_find(src, key, kind, NULL) ? (int64_t)1 : (int64_t)0;
}

FOLD_API FoldValue fold_map_len(FoldMap src) {
    FoldValue out;
    memset(&out, 0, sizeof out);
    out.reason = fold_bytes_empty();
    if (src.count > (size_t)INT64_MAX) {
        out.failed = 1;
        return out;
    }
    out.i64 = (int64_t)src.count;
    return out;
}

FOLD_API FoldMap fold_map_put(FoldMap src, const void *key, const void *val, int kind) {
    size_t found = 0;
    int hit;
    size_t n;
    size_t key_bytes;
    size_t val_bytes;
    uint8_t *keys;
    uint8_t *vals;
    FoldMap out;
    if (src.key_stride == 0 || src.val_stride == 0 || key == NULL || val == NULL) {
        fold_oom();
    }
    hit = fold_map_find(src, key, kind, &found);
    if (hit) {
        n = src.count;
    } else {
        if (src.count == SIZE_MAX) {
            fold_oom();
        }
        n = src.count + 1;
    }
    if (n > SIZE_MAX / src.key_stride || n > SIZE_MAX / src.val_stride) {
        fold_oom();
    }
    key_bytes = n * src.key_stride;
    val_bytes = n * src.val_stride;
    keys = fold_map_block(key_bytes);
    vals = fold_map_block(val_bytes);
    if (src.count != 0 && src.keys != NULL) {
        memcpy(keys, src.keys, src.count * src.key_stride);
    }
    if (src.count != 0 && src.vals != NULL) {
        memcpy(vals, src.vals, src.count * src.val_stride);
    }
    if (hit) {
        memcpy(vals + found * src.val_stride, val, src.val_stride);
    } else {
        memcpy(keys + src.count * src.key_stride, key, src.key_stride);
        memcpy(vals + src.count * src.val_stride, val, src.val_stride);
    }
    out.keys = keys;
    out.vals = vals;
    out.count = n;
    out.key_stride = src.key_stride;
    out.val_stride = src.val_stride;
    return out;
}

FOLD_API void fold_lines(FoldBytes text, FoldLines *out) {
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


FOLD_API void fold_lines_free(FoldLines *lines) {
    if (lines != NULL && lines->items != NULL) {
        free(lines->items);
        lines->items = NULL;
        lines->count = 0;
    }
}
