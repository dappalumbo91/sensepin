/* Probe 01 grades. Contract: probes/01-grades/task.md. */
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

static int parse_grade(char *line, int64_t *out, int *name_len) {
    char *space = strchr(line, ' ');
    char *scan;

    if (space == NULL || space == line || strchr(space + 1, ' ') != NULL) {
        return 0;
    }
    for (scan = line; scan < space; scan++) {
        if (!name_byte((unsigned char)*scan)) {
            return 0;
        }
    }
    if (!parse_i64(space + 1, out)) {
        return 0;
    }
    *name_len = (int)(space - line);
    return 1;
}

int main(int argc, char **argv) {
    FILE *file;
    long size;
    char *data;
    size_t start;
    int64_t count = 0;
    int64_t sum = 0;
    int64_t low = 0;
    int64_t high = 0;
    char *max_name = NULL;
    int any = 0;
    int line_no = 1;

#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);
#endif
    if (argc != 2) {
        die("usage: grades <file>");
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
        int64_t value;
        int name_len;
        char *name;

        while (end < (size_t)size && data[end] != '\n') {
            end++;
        }
        saved = data[end];
        data[end] = '\0';
        if (end > start && data[end - 1] == '\r') {
            data[end - 1] = '\0';
        }
        if (!parse_grade(data + start, &value, &name_len) || !add_i64(&sum, value)) {
            fprintf(stderr, "bad line %d: %s\n", line_no, data + start);
            free(data);
            return 1;
        }
        data[start + (size_t)name_len] = '\0';
        name = data + start;
        if (!any) {
            low = high = value;
            max_name = name;
            any = 1;
        } else {
            if (value < low) {
                low = value;
            }
            if (value > high) {
                high = value;
                max_name = name;
            }
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
    printf("mean %lld\n", (long long)(sum / count));
    printf("min %lld\n", (long long)low);
    printf("max %lld\n", (long long)high);
    printf("name %s\n", max_name);
    free(data);
    return 0;
}
