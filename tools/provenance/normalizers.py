#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Shared literal-aware normalizers for provenance verification.

Each normalizer removes comments and insignificant whitespace while
preserving string literals (including comment-like text inside them)
verbatim. The canonical form is the concatenation of significant tokens,
so it is insensitive to whitespace and comments but sensitive to every
other byte.

Languages: php (real tokenizer via PHP token_get_all), sql, cpp, sh, python.
"""
import base64
import io
import re
import subprocess
import tokenize


# --------------------------------------------------------------------------
# PHP — real tokenizer: PHP's own token_get_all via CLI
# --------------------------------------------------------------------------

def _php_body(code):
    """Strip a leading PHP open tag; fragments are lexed in PHP mode."""
    return re.sub(r'^\s*<\?(?:php|=)?', '', code)


def _php_run(src, payload):
    proc = subprocess.run(
        ['php', '-r', src],
        input=payload, capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'php tokenizer failed: {proc.stderr.strip()}')
    return proc.stdout


_PHP_TOKENIZER_SRC = r'''
$code = stream_get_contents(STDIN);
$tokens = @token_get_all($code);
if ($tokens === false) { fwrite(STDERR, "token_get_all failed\n"); exit(2); }
foreach ($tokens as $t) {
    if (is_array($t)) {
        $name = token_name($t[0]);
        echo $name, "\t", base64_encode($t[1]), "\n";
    } else {
        echo "CHAR\t", base64_encode($t), "\n";
    }
}
'''

_PHP_DROP = {'T_WHITESPACE', 'T_COMMENT', 'T_DOC_COMMENT'}


def normalize_php(code):
    payload = '<?php ' + _php_body(code)
    out = _php_run(_PHP_TOKENIZER_SRC, payload)
    parts = []
    for line in out.split('\n'):
        if not line:
            continue
        name, _, b64 = line.partition('\t')
        if name in _PHP_DROP:
            continue
        parts.append(base64.b64decode(b64).decode('utf-8', 'surrogateescape'))
    return ''.join(parts)


_PHP_SPAN_SRC = r'''
$code = stream_get_contents(STDIN);
$tokens = @token_get_all($code);
$pos = 0;
$string_types = array_filter(
    [T_CONSTANT_ENCAPSED_STRING, T_ENCAPSED_AND_WHITESPACE,
     T_CURLY_OPEN, T_DOLLAR_OPEN_CURLY_BRACES]
    + (defined('T_START_HEREDOC') ? [T_START_HEREDOC, T_END_HEREDOC] : [])
    + (defined('T_START_NOWDOC') ? [T_START_NOWDOC, T_END_NOWDOC] : []),
    function($c) { return $c !== null; });
foreach ($tokens as $t) {
    $text = is_array($t) ? $t[1] : $t;
    $len = strlen($text);
    if (is_array($t) && in_array($t[0], $string_types, true)) {
        echo $pos, "\t", $pos + $len, "\n";
    }
    $pos += $len;
}
'''

_PROLOGUE = '<?php '


def php_string_spans(code):
    """Return (start, end) char spans of PHP string literals in `code`.

    Offsets are relative to the open-tag-stripped body, which is what
    substitution scope checks operate on.
    """
    body = _php_body(code)
    payload = _PROLOGUE + body
    out = _php_run(_PHP_SPAN_SRC, payload)
    # PHP reports BYTE offsets (strlen); Python strings are char-indexed.
    # Map byte spans back to char spans via UTF-8 decoding.
    body_b = body.encode('utf-8')

    def b2c(byte_pos):
        return len(body_b[:byte_pos].decode('utf-8', 'surrogateescape'))

    spans = []
    for line in out.split('\n'):
        if not line:
            continue
        s, e = line.split('\t')
        spans.append((b2c(int(s) - len(_PROLOGUE)),
                      b2c(int(e) - len(_PROLOGUE))))
    return spans


# --------------------------------------------------------------------------
# Generic literal-aware scanner for sql / cpp / sh
# --------------------------------------------------------------------------

def _scan(code, lang):
    """Return (normalized, string_spans, comments).

    normalized: concatenation of string literals (verbatim, delimiters
    included) and non-whitespace code characters; comments removed.
    string_spans: (start, end) offsets in `code` covered by literals.
    """
    out = []
    spans = []
    comments = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        two = code[i:i + 2]

        # ---- comments ----
        if lang == 'sql':
            if two == '--':
                j = code.find('\n', i)
                k = n if j < 0 else j
                comments.append(code[i:k])
                i = k
                continue
            if code.startswith('/*', i):
                depth, j = 1, i + 2
                while j < n and depth:
                    if code.startswith('/*', j):
                        depth += 1; j += 2
                    elif code.startswith('*/', j):
                        depth -= 1; j += 2
                    else:
                        j += 1
                comments.append(code[i:j])
                i = j
                continue
        elif lang == 'cpp':
            if two == '//':
                j = code.find('\n', i)
                k = n if j < 0 else j
                comments.append(code[i:k])
                i = k
                continue
            if code.startswith('/*', i):
                j = code.find('*/', i + 2)
                k = n if j < 0 else j + 2
                comments.append(code[i:k])
                i = k
                continue
        elif lang == 'sh':
            if c == '#' and (i == 0 or code[i - 1] in ' \t\n;|&()<>{}'):
                j = code.find('\n', i)
                k = n if j < 0 else j
                comments.append(code[i:k])
                i = k
                continue

        # ---- literals ----
        if lang == 'sql':
            m = re.match(r'\$[A-Za-z_0-9]*\$', code[i:])
            if m:
                tag = m.group(0)
                end = code.find(tag, i + len(tag))
                j = n if end < 0 else end + len(tag)
                lit = code[i:j]
                spans.append((i, j))
                out.append(lit)
                i = j
                continue
            if c == "'" or (c in 'Ee' and i + 1 < n and code[i + 1] == "'"):
                esc = c in 'Ee'
                start = i
                i += 2 if esc else 1
                while i < n:
                    if esc and code[i] == '\\':
                        i += 2
                        continue
                    if code[i] == "'":
                        if i + 1 < n and code[i + 1] == "'":
                            i += 2
                            continue
                        i += 1
                        break
                    i += 1
                lit = code[start:i]
                spans.append((start, i))
                out.append(lit)
                continue
            if c == '"':
                start = i
                i += 1
                while i < n:
                    if code[i] == '"':
                        if i + 1 < n and code[i + 1] == '"':
                            i += 2
                            continue
                        i += 1
                        break
                    i += 1
                lit = code[start:i]
                spans.append((start, i))
                out.append(lit)
                continue
        elif lang == 'cpp':
            m = re.match(r'R"([A-Za-z0-9_]{0,16})\(', code[i:])
            if m:
                delim = m.group(1)
                close = ')' + delim + '"'
                start = i
                end = code.find(close, i + m.end())
                j = n if end < 0 else end + len(close)
                lit = code[start:j]
                spans.append((start, j))
                out.append(lit)
                i = j
                continue
            if c in '"\'':
                quote = c
                start = i
                i += 1
                while i < n:
                    if code[i] == '\\':
                        i += 2
                        continue
                    if code[i] == quote:
                        i += 1
                        break
                    i += 1
                lit = code[start:i]
                spans.append((start, i))
                out.append(lit)
                continue
        elif lang == 'sh':
            if c == "'":
                start = i
                j = code.find("'", i + 1)
                i = n if j < 0 else j + 1
                lit = code[start:i]
                spans.append((start, i))
                out.append(lit)
                continue
            if c == '"':
                start = i
                i += 1
                while i < n:
                    if code[i] == '\\':
                        i += 2
                        continue
                    if code[i] == '"':
                        i += 1
                        break
                    i += 1
                lit = code[start:i]
                spans.append((start, i))
                out.append(lit)
                continue
            m = re.match(r'<<-?\s*[\'"]?([A-Za-z_][A-Za-z0-9_]*)[\'"]?', code[i:])
            if m:
                delim = m.group(1)
                out.append(code[i:i + m.end()])
                i += m.end()
                nl = code.find('\n', i)
                if nl < 0:
                    break
                body_start = nl + 1
                lines = code[body_start:].split('\n')
                k = 0
                while k < len(lines):
                    if lines[k].strip() == delim:
                        break
                    k += 1
                body_end = body_start + sum(len(l) + 1 for l in lines[:k])
                lit = code[body_start:body_end]
                spans.append((body_start, body_end))
                out.append(lit)
                i = body_end
                continue

        if not c.isspace():
            out.append(c)
        i += 1

    return ''.join(out), spans, comments


def normalize_sql(code):
    return _scan(code, 'sql')[0]


def normalize_cpp(code):
    return _scan(code, 'cpp')[0]


def normalize_sh(code):
    return _scan(code, 'sh')[0]


def normalize_python(code):
    toks = tokenize.generate_tokens(io.StringIO(code).readline)
    parts = []
    for tok in toks:
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                        tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
                        tokenize.ENDMARKER):
            continue
        parts.append(tok.string)
    return ''.join(parts)


NORMALIZERS = {
    'php': normalize_php,
    'sql': normalize_sql,
    'cpp': normalize_cpp,
    'sh': normalize_sh,
    'python': normalize_python,
}


def normalize(code, lang):
    fn = NORMALIZERS.get(lang)
    if fn is None:
        raise ValueError(f'no normalizer for language: {lang}')
    return fn(code)


def iter_comments(code, lang):
    """Return list of comment texts (with delimiters) in source order."""
    if lang == 'php':
        body = _php_body(code)
        out = _php_run(_PHP_TOKENIZER_SRC, '<?php ' + body)
        comments = []
        for line in out.split('\n'):
            if not line:
                continue
            name, _, b64 = line.partition('\t')
            if name in ('T_COMMENT', 'T_DOC_COMMENT'):
                comments.append(base64.b64decode(b64).decode('utf-8', 'surrogateescape'))
        return comments
    if lang in ('sql', 'cpp', 'sh'):
        return _scan(code, lang)[2]
    if lang == 'python':
        return [tok.string for tok in tokenize.generate_tokens(io.StringIO(code).readline)
                if tok.type == tokenize.COMMENT]
    return []


def string_spans(code, lang):
    """Char spans of string literals, for substitution scope checks."""
    if lang == 'php':
        body = _php_body(code)
        return [(s, e) for s, e in php_string_spans(code)]
    if lang in ('sql', 'cpp', 'sh'):
        return _scan(code, lang)[1]
    if lang == 'python':
        return [(tok.start[1], tok.end[1])
                for tok in tokenize.generate_tokens(io.StringIO(code).readline)
                if tok.type == tokenize.STRING]
    return []
