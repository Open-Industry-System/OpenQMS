"""Conservative PostgreSQL SQL lexer for tenant snapshot identifier rewriting.

Only identifier tokens are transformed. Comments and quoted string literals are
opaque; only the executable outer AS $body$ of CREATE FUNCTION/PROCEDURE is
scanned recursively. Nested dollar-quoted values stay opaque. Unknown lexemes
fail closed rather than allowing an unexamined schema-qualified reference
through.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Token:
    kind: str
    text: str

    @property
    def identifier(self) -> str | None:
        if self.kind == "ident":
            return self.text.lower()
        if self.kind == "quoted_ident":
            return self.text[1:-1].replace('""', '"')
        return None


_DOLLAR = re.compile(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9$]*")


def scan_sql(source: str) -> list[Token]:
    """Scan PG identifiers, trivia, strings and dollar-quoted bodies losslessly."""
    tokens: list[Token] = []
    i = 0
    while i < len(source):
        start = i
        c = source[i]
        if c.isspace():
            while i < len(source) and source[i].isspace():
                i += 1
            kind = "space"
        elif source.startswith("--", i):
            end = source.find("\n", i + 2)
            i = end if end != -1 else len(source)
            kind = "comment"
        elif source.startswith("/*", i):
            depth = 1
            i += 2
            while depth and i < len(source):
                if source.startswith("/*", i):
                    depth += 1; i += 2
                elif source.startswith("*/", i):
                    depth -= 1; i += 2
                else:
                    i += 1
            if depth:
                raise ValueError("Unterminated SQL block comment")
            kind = "comment"
        elif c in ("'", '"'):
            # E'...' and U&'...' use backslash escapes; U& identifiers are
            # deliberately rejected because decoding them needs PG's Unicode rules.
            if c == '"' and source[max(0, i - 2):i].upper() == "U&":
                raise ValueError("Unicode-escaped quoted identifiers need explicit review")
            escaped = c == "'" and (source[max(0, i - 2):i].upper() == "U&" or
                                     (i > 0 and source[i - 1] in "Ee" and
                                      (i == 1 or not (source[i - 2].isalnum() or source[i - 2] == "_"))))
            i += 1
            while i < len(source):
                if escaped and source[i] == "\\":
                    i += 2
                elif source.startswith(c * 2, i):
                    i += 2
                elif source[i] == c:
                    i += 1
                    break
                else:
                    i += 1
            else:
                raise ValueError("Unterminated SQL quoted token")
            kind = "string" if c == "'" else "quoted_ident"
        elif c == "$" and (match := _DOLLAR.match(source, i)):
            marker = match.group()
            end = source.find(marker, match.end())
            if end == -1:
                raise ValueError("Unterminated SQL dollar quote")
            i = end + len(marker)
            kind = "dollar"
        elif match := _IDENT.match(source, i):
            i = match.end()
            kind = "ident"
        elif c.isascii() and (c.isdigit() or c in "()[]{}.,;:+-*/%=<>!~^|&?#@$\\"):
            i += 1
            kind = "symbol"
        else:
            raise ValueError(f"Unreviewed SQL lexeme at offset {i}: {source[i:i + 20]!r}")
        tokens.append(Token(kind, source[start:i]))
    return tokens


def _next_code(tokens: list[Token], start: int) -> int:
    while start < len(tokens) and tokens[start].kind in {"space", "comment"}:
        start += 1
    return start


def _routine_declaration(tokens: list[Token]) -> bool:
    """Recognize the CREATE FUNCTION/PROCEDURE grammar prefix, not a nearby AS."""
    code = [token for token in tokens if token.kind not in {"space", "comment"}]
    if not code or code[0].kind != "ident" or code[0].identifier != "create":
        return False
    pos = 1
    if (len(code) > 2 and code[1].identifier == "or" and code[2].identifier == "replace"):
        pos = 3
    return pos < len(code) and code[pos].kind == "ident" and code[pos].identifier in {"function", "procedure"}


def _previous_code(tokens: list[Token], start: int) -> int:
    while start >= 0 and tokens[start].kind in {"space", "comment"}:
        start -= 1
    return start


def rewrite_qualifiers(source: str, schema: str, *, known_public: frozenset[str] | None = None,
                       shared_public: frozenset[str] = frozenset(), collapse_space: bool = False,
                       qualify_digest: bool = False, canonicalize_shared_digest: bool = False,
                       _inside_routine_body: bool = False) -> str:
    """Remove only the selected schema's identifier qualification.

    In generation, known_public is a complete allowlist and unknown public
    qualifications fail. In parity, each side strips *only its own* schema;
    foreign public business references remain observable differences.
    """
    tokens = scan_sql(source)
    routine = not _inside_routine_body and _routine_declaration(tokens)
    skip = set()
    replacements: dict[int, str] = {}
    for i, token in enumerate(tokens):
        if token.kind == "dollar":
            # Dollar syntax is also a *data literal* (including DEFAULT and
            # nested RETURN $inner$...$inner$). Only the declaration's outer
            # AS $body$ is executable source and may be scanned recursively.
            prev = _previous_code(tokens, i - 1)
            if routine and prev >= 0 and tokens[prev].kind == "ident" and tokens[prev].identifier == "as":
                marker = _DOLLAR.match(token.text).group()
                body = token.text[len(marker):-len(marker)]
                replacements[i] = marker + rewrite_qualifiers(
                    body, schema, known_public=known_public, shared_public=shared_public,
                    qualify_digest=qualify_digest, canonicalize_shared_digest=canonicalize_shared_digest,
                    _inside_routine_body=True,
                ) + marker
            continue
        if token.identifier is None:
            continue
        dot = _next_code(tokens, i + 1)
        target = _next_code(tokens, dot + 1)
        qualified = (dot < len(tokens) and tokens[dot].text == "." and
                     target < len(tokens) and tokens[target].identifier is not None)
        if token.identifier == "public" and qualified and known_public is not None:
            if tokens[target].identifier not in known_public | shared_public:
                raise ValueError(f"Unreviewed public reference: {tokens[target].text}")
        if token.identifier == "public" and qualified and canonicalize_shared_digest and tokens[target].identifier == "digest":
            skip.update(range(i, target))
        elif token.identifier == schema and qualified and tokens[target].identifier not in shared_public:
            skip.update(range(i, target))
        if qualify_digest and token.identifier == "digest" and not qualified:
            # The only snapshot function invoking pgcrypto is verify_version_hash.
            # Do not touch a qualified call, declaration, or a string literal.
            prev = i - 1
            while prev >= 0 and tokens[prev].kind in {"space", "comment"}:
                prev -= 1
            if (prev < 0 or tokens[prev].text != ".") and dot < len(tokens) and tokens[dot].text == "(":
                replacements[i] = "public." + token.text
    parts = []
    for i, token in enumerate(tokens):
        if i in skip:
            continue
        value = replacements.get(i, token.text)
        if collapse_space and token.kind in {"space", "comment"}:
            if parts and parts[-1] != " ":
                parts.append(" ")
        else:
            parts.append(value)
    return "".join(parts).strip() if collapse_space else "".join(parts)
