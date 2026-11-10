/* Direct checks for the gauge runtime. The language cannot spell a zero byte inside a path. */
#define FOLD_NO_ENTRY
#include "runtime.c"

#include <stdio.h>
#include <string.h>

static int expect_i64(const char *name, FoldValue got, int failed, int64_t value) {
    if (got.failed != failed || (!failed && got.i64 != value)) {
        fprintf(stderr, "%s failed=%d value=%lld\n", name, got.failed, (long long)got.i64);
        return 1;
    }
    return 0;
}

static int success_cases(void) {
    int bad = 0;
    unsigned char *block;
    unsigned char *more;
    int i;
    FoldBytes dec;
    FoldBytes path;
    FoldBytes miss;
    FoldValue opened;
    const char *min_text = "-9223372036854775808";

    block = (unsigned char *)fold_alloc(32);
    for (i = 0; i < 32; i++) {
        block[i] = (unsigned char)i;
    }
    (void)fold_alloc(4096);
    more = (unsigned char *)fold_alloc(10000);
    memset(more, 0x5A, 10000);
    for (i = 0; i < 32; i++) {
        if (block[i] != (unsigned char)i) {
            fprintf(stderr, "arena moved a live block\n");
            return 1;
        }
    }

    bad += expect_i64("max+1", fold_add(INT64_MAX, 1), 1, 0);
    bad += expect_i64("min-1", fold_add(INT64_MIN, -1), 1, 0);
    bad += expect_i64("sub min", fold_sub(0, INT64_MIN), 1, 0);
    bad += expect_i64("neg min", fold_neg(INT64_MIN), 1, 0);
    bad += expect_i64("max+0", fold_add(INT64_MAX, 0), 0, INT64_MAX);
    bad += expect_i64("min+0", fold_add(INT64_MIN, 0), 0, INT64_MIN);
    bad += expect_i64("parse min", fold_i64(fold_bytes_view((const uint8_t *)min_text, strlen(min_text))), 0, INT64_MIN);
    bad += expect_i64("mul", fold_mul(6, 7), 0, 42);
    bad += expect_i64("mul min", fold_mul(INT64_MIN, -1), 1, 0);
    bad += expect_i64("mul one", fold_mul(INT64_MIN, 1), 0, INT64_MIN);
    bad += expect_i64("mul zero", fold_mul(0, INT64_MIN), 0, 0);
    bad += expect_i64("mul neg", fold_mul(-3, -4), 0, 12);
    bad += expect_i64("mul max", fold_mul(INT64_MAX, 2), 1, 0);

    dec = fold_dec(INT64_MIN);
    if (dec.n != strlen(min_text) || memcmp(dec.p, min_text, dec.n) != 0) {
        fprintf(stderr, "decimal min changed\n");
        bad += 1;
    }

    path = fold_bytes_view((const uint8_t *)"a\0b", 3);
    miss = fold_bytes_view((const uint8_t *)"MISS", 4);
    opened = fold_open(
        path,
        10,
        miss,
        fold_bytes_view((const uint8_t *)"EMPTY", 5),
        fold_bytes_view((const uint8_t *)"LARGE", 5));
    if (!opened.failed || opened.reason.n != 7 || memcmp(opened.reason.p, "MISSa\0b", 7) != 0) {
        fprintf(stderr, "nul path was not rejected with the path bytes\n");
        bad += 1;
    }

    {
        FoldMap older;
        FoldMap newer;
        FoldMap zeros;
        FoldMap text;
        FoldMap huge;
        int64_t key = 1;
        int64_t first = 10;
        int64_t second = 20;
        int64_t got = 0;
        int64_t one = 1;
        int64_t two = 2;
        int64_t three = 3;
        double pos = 0.0;
        double neg = -0.0;
        size_t index = 7;
        char buf[2] = {'h', 'i'};
        FoldBytes hi;
        FoldBytes same;
        FoldBytes empty_a;
        FoldBytes empty_b;
        FoldValue counted;
        older = fold_map_empty(sizeof key, sizeof first);
        older = fold_map_put(older, &key, &first, FOLD_KEY_I64);
        newer = fold_map_put(older, &key, &second, FOLD_KEY_I64);
        memcpy(&got, older.vals, sizeof got);
        if (older.count != 1 || got != 10) {
            fprintf(stderr, "map put changed the earlier map\n");
            bad += 1;
        }
        memcpy(&got, newer.vals, sizeof got);
        if (newer.count != 1 || got != 20 || !fold_map_find(newer, &key, FOLD_KEY_I64, &index) || index != 0) {
            fprintf(stderr, "map replace did not keep the first position\n");
            bad += 1;
        }
        zeros = fold_map_empty(sizeof pos, sizeof one);
        zeros = fold_map_put(zeros, &pos, &one, FOLD_KEY_F64);
        zeros = fold_map_put(zeros, &neg, &two, FOLD_KEY_F64);
        memcpy(&got, zeros.vals, sizeof got);
        if (zeros.count != 1 || got != 2 || fold_map_has(zeros, &pos, FOLD_KEY_F64) != 1) {
            fprintf(stderr, "map f64 zero keys did not match\n");
            bad += 1;
        }
        hi = fold_bytes_view((const uint8_t *)"hi", 2);
        same = fold_bytes_view((const uint8_t *)buf, 2);
        empty_a = fold_bytes_empty();
        empty_b = fold_bytes_view((const uint8_t *)"", 0);
        text = fold_map_empty(sizeof hi, sizeof one);
        text = fold_map_put(text, &hi, &one, FOLD_KEY_BYTES);
        text = fold_map_put(text, &same, &two, FOLD_KEY_BYTES);
        text = fold_map_put(text, &empty_a, &three, FOLD_KEY_BYTES);
        text = fold_map_put(text, &empty_b, &one, FOLD_KEY_BYTES);
        if (text.count != 2 || fold_map_has(text, &hi, FOLD_KEY_BYTES) != 1) {
            fprintf(stderr, "map bytes keys did not match by contents\n");
            bad += 1;
        }
        huge = fold_map_empty(sizeof key, sizeof first);
        huge.count = (size_t)INT64_MAX + 1;
        counted = fold_map_len(huge);
        if (!counted.failed) {
            fprintf(stderr, "map len accepted a count past i64\n");
            bad += 1;
        }
    }
    return bad;
}

static int wrap_case(void) {
    unsigned char *block = (unsigned char *)fold_alloc(8);
    memset(block, 1, 8);
    fold_chunk->used = 100;
    fold_chunk->cap = 128;
    /* used + n wraps, and the new chunk's size also wraps. Both must exit. */
    (void)fold_alloc(SIZE_MAX - 50);
    fprintf(stderr, "wrap returned a pointer\n");
    return 2;
}

int main(int argc, char **argv) {
    fold_init(argc, argv);
    if (argc > 1 && strcmp(argv[1], "wrap") == 0) {
        return wrap_case();
    }
    return success_cases();
}
