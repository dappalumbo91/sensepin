/* Probe 02 shelf. Contract: probes/02-shelf/task.md. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#define MAX_BYTES 1048576

static void die(const char *message) {
    fprintf(stderr, "%s\n", message);
    exit(1);
}

static int name_byte(unsigned char byte) {
    return (byte >= 'A' && byte <= 'Z') || (byte >= 'a' && byte <= 'z') ||
           (byte >= '0' && byte <= '9') || byte == '_';
}

static int parse_i64(const char *text, int64_t *out) {
    const char *body;
    char *end;
    long long value;

    if (text[0] == '\0' || strcmp(text, "+") == 0 || strcmp(text, "-") == 0) {
        return 0;
    }
    if (text[0] != '+' && text[0] != '-' && (text[0] < '0' || text[0] > '9')) {
        return 0;
    }
    body = (text[0] == '+' || text[0] == '-') ? text + 1 : text;
    if (body[0] == '\0') {
        return 0;
    }
    for (const char *p = body; *p != '\0'; p++) {
        if (*p < '0' || *p > '9') {
            return 0;
        }
    }
    errno = 0;
    value = strtoll(text, &end, 10);
    if (errno == ERANGE || end == text || *end != '\0') {
        return 0;
    }
    *out = (int64_t)value;
    return 1;
}

static int parse_span(const char *text, size_t n, int64_t *out) {
    char buf[64];
    if (n == 0 || n >= sizeof buf) {
        return 0;
    }
    memcpy(buf, text, n);
    buf[n] = '\0';
    return parse_i64(buf, out);
}

static int add_i64(int64_t *sum, int64_t value) {
    if (value > 0 && *sum > INT64_MAX - value) {
        return 0;
    }
    if (value < 0 && *sum < INT64_MIN - value) {
        return 0;
    }
    *sum += value;
    return 1;
}

static int mul_i64(int64_t a, int64_t b, int64_t *out) {
    int64_t aa;
    int64_t bb;
    if (a == 0 || b == 0) {
        *out = 0;
        return 1;
    }
    if (a == INT64_MIN) {
        *out = b == 1 ? a : 0;
        return b == 1;
    }
    if (b == INT64_MIN) {
        *out = a == 1 ? b : 0;
        return a == 1;
    }
    aa = a < 0 ? -a : a;
    bb = b < 0 ? -b : b;
    if (aa > INT64_MAX / bb) {
        return 0;
    }
    *out = a * b;
    return 1;
}

static int parse_row(char *line, int *name_len, int64_t *qty, int64_t *price) {
    char *s1 = strchr(line, ' ');
    char *s2;
    char *scan;
    int64_t q;
    int64_t p;

    if (s1 == NULL || s1 == line) {
        return 0;
    }
    s2 = strchr(s1 + 1, ' ');
    if (s2 == NULL || s2 == s1 + 1 || strchr(s2 + 1, ' ') != NULL) {
        return 0;
    }
    for (scan = line; scan < s1; scan++) {
        if (!name_byte((unsigned char)*scan)) {
            return 0;
        }
    }
    if (!parse_span(s1 + 1, (size_t)(s2 - (s1 + 1)), &q) || !parse_i64(s2 + 1, &p)) {
        return 0;
    }
    *name_len = (int)(s1 - line);
    *qty = q;
    *price = p;
    return 1;
}

int main(int argc, char **argv) {
    FILE *file;
    long size;
    char *data;
    size_t start;
    int64_t count = 0;
    int64_t pieces = 0;
    int64_t worth = 0;
    int64_t high = 0;
    char *item = NULL;
    int item_len = 0;
    int any = 0;
    int line_no = 1;

#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);
#endif
    if (argc != 2) {
        die("usage: shelf <file>");
    }
    file = fopen(argv[1], "rb");
    if (file == NULL) {
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    size = ftell(file);
    if (size < 0) {
        fclose(file);
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    if ((unsigned long)size > MAX_BYTES) {
        fclose(file);
        die("file too large");
    }
    if (size == 0) {
        fclose(file);
        die("empty file");
    }
    if (fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    data = (char *)malloc((size_t)size + 1);
    if (data == NULL) {
        fclose(file);
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    if (fread(data, 1, (size_t)size, file) != (size_t)size) {
        free(data);
        fclose(file);
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    fclose(file);
    data[size] = '\0';

    start = 0;
    while (start < (size_t)size) {
        size_t end = start;
        char saved;
        int name_len;
        int64_t qty;
        int64_t price;
        int64_t line_value;
        char *name;

        while (end < (size_t)size && data[end] != '\n') {
            end++;
        }
        saved = data[end];
        data[end] = '\0';
        if (end > start && data[end - 1] == '\r') {
            data[end - 1] = '\0';
        }
        if (!parse_row(data + start, &name_len, &qty, &price) ||
            !mul_i64(qty, price, &line_value) || !add_i64(&pieces, qty) ||
            !add_i64(&worth, line_value)) {
            fprintf(stderr, "bad line %d: %s\n", line_no, data + start);
            free(data);
            return 1;
        }
        name = data + start;
        if (!any) {
            high = line_value;
            item = name;
            item_len = name_len;
            any = 1;
        } else if (line_value > high) {
            high = line_value;
            item = name;
            item_len = name_len;
        }
        count++;
        if (saved != '\n') {
            break;
        }
        start = end + 1;
        line_no++;
        if (start == (size_t)size) {
            break;
        }
    }

    printf("count %lld\n", (long long)count);
    printf("pieces %lld\n", (long long)pieces);
    printf("value %lld\n", (long long)worth);
    printf("item %.*s\n", item_len, item);
    free(data);
    return 0;
}
