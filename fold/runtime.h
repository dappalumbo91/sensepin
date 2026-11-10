/* Sensepin gauge runtime. Behavior is fold/SPEC.md. */
#ifndef FOLD_RUNTIME_H
#define FOLD_RUNTIME_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) && defined(FOLD_BUILD_DLL)
#define FOLD_API __declspec(dllexport)
#elif defined(_WIN32) && defined(FOLD_USE_DLL)
#define FOLD_API __declspec(dllimport)
#else
#define FOLD_API
#endif

#if defined(__clang__) || defined(__GNUC__)
#define FOLD_NORETURN __attribute__((noreturn))
#else
#define FOLD_NORETURN
#endif

typedef struct FoldBytes {
    const uint8_t *p;
    size_t n;
} FoldBytes;

typedef struct FoldList {
    const uint8_t *items;
    size_t count;
    size_t stride;
} FoldList;

/* Key kinds for fold_map_put, fold_map_find, and fold_map_has. */
#define FOLD_KEY_I64 0
#define FOLD_KEY_F64 1
#define FOLD_KEY_BYTES 2

typedef struct FoldMap {
    const uint8_t *keys;
    const uint8_t *vals;
    size_t count;
    size_t key_stride;
    size_t val_stride;
} FoldMap;

typedef struct FoldValue {
    int failed;
    FoldBytes reason;
    FoldBytes bytes;
    int64_t i64;
    double f64;
    FoldList list;
    FoldMap map;
    const void *obj;
} FoldValue;

typedef struct FoldLine {
    FoldBytes text;
    int64_t n;
} FoldLine;

typedef struct FoldLines {
    FoldLine *items;
    size_t count;
} FoldLines;

FOLD_API FoldBytes fold_bytes_empty(void);
FOLD_API FoldBytes fold_bytes_view(const uint8_t *p, size_t n);
FOLD_API FoldBytes fold_cat(FoldBytes a, FoldBytes b);
FOLD_API FoldBytes fold_dec(int64_t value);
FOLD_API FoldBytes fold_dec_f64(double value);
FOLD_API double fold_f64_bits(uint64_t bits);
FOLD_API const void *fold_box(const void *p, size_t n);
FOLD_NORETURN FOLD_API void fold_fail(FoldBytes message);
FOLD_API void fold_write(FoldBytes message);
FOLD_API void fold_enter(void);
FOLD_API void fold_leave(void);
FOLD_API void fold_init(int argc, char **argv);
FOLD_API int64_t fold_argc(void);
FOLD_API FoldValue fold_arg(int64_t index);
FOLD_API FoldValue fold_i64(FoldBytes text);
FOLD_API FoldValue fold_add(int64_t a, int64_t b);
FOLD_API FoldValue fold_sub(int64_t a, int64_t b);
FOLD_API FoldValue fold_div(int64_t a, int64_t b);
FOLD_API FoldValue fold_mul(int64_t a, int64_t b);
FOLD_API FoldValue fold_fadd(double a, double b);
FOLD_API FoldValue fold_fsub(double a, double b);
FOLD_API FoldValue fold_fmul(double a, double b);
FOLD_API FoldValue fold_fdiv(double a, double b);
FOLD_API FoldValue fold_fneg(double value);
FOLD_API FoldValue fold_f64_from_i64(int64_t value);
FOLD_API FoldValue fold_i64_from_f64(double value);
FOLD_API FoldValue fold_neg(int64_t value);
FOLD_API FoldValue fold_open(FoldBytes path, int64_t limit, FoldBytes missing, FoldBytes empty, FoldBytes large);
FOLD_API FoldValue fold_len(FoldBytes text);
FOLD_API FoldValue fold_before(FoldBytes text, FoldBytes sep);
FOLD_API FoldValue fold_after(FoldBytes text, FoldBytes sep);
FOLD_API FoldValue fold_holds(FoldBytes text, FoldBytes sep);
FOLD_API FoldValue fold_byte(int64_t value);
FOLD_API FoldValue fold_set_byte(FoldBytes text, int64_t index, int64_t value);
FOLD_API FoldValue fold_save(FoldBytes path, FoldBytes data);
FOLD_API FoldList fold_list_empty(size_t stride);
FOLD_API uint8_t *fold_list_alloc(size_t count, size_t stride);
FOLD_API FoldList fold_list_push(FoldList xs, const void *elem, size_t stride);
FOLD_API FoldValue fold_list_len(FoldList xs);
FOLD_API int fold_list_index(FoldList xs, int64_t index);
FOLD_API FoldMap fold_map_empty(size_t key_stride, size_t val_stride);
FOLD_API FoldMap fold_map_put(FoldMap src, const void *key, const void *val, int kind);
FOLD_API FoldValue fold_map_len(FoldMap src);
FOLD_API int fold_map_find(FoldMap src, const void *key, int kind, size_t *index);
FOLD_API int64_t fold_map_has(FoldMap src, const void *key, int kind);
FOLD_API void fold_lines(FoldBytes text, FoldLines *out);
FOLD_API void fold_lines_free(FoldLines *lines);

#endif
