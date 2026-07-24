"""Sanitization for user-authored page content.

Custom HTML/CSS entered in the website builder renders on the PUBLIC site, so it is a stored-XSS
vector. These functions are the primary defense (CSP + an iframe sandbox on raw-script blocks are
the backstops). Everything servable passes through here; the public API only ever serves the
sanitized output.
"""

from __future__ import annotations

import re

import nh3

# Allowlisted tags for a custom-HTML block. No <script>, <style>, <iframe>, <object>, <embed>,
# <form>, <link>, <meta> — nh3 drops everything not listed.
_ALLOWED_TAGS: set[str] = {
    "a", "abbr", "b", "blockquote", "br", "caption", "code", "col", "colgroup", "div",
    "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img",
    "li", "mark", "ol", "p", "pre", "section", "small", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}

# Per-tag attribute allowlist. Notably NO `style` (styling goes through custom CSS, which is
# separately sanitized + scoped) and NO event handlers (nh3 drops on* anyway).
_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height", "loading"},
    "*": {"class", "id"},
}

# URL schemes permitted on href/src. No `javascript:`, no `data:` (blocks data-URI script vectors).
_ALLOWED_SCHEMES: set[str] = {"http", "https", "mailto"}


def sanitize_html(raw: str) -> str:
    """Return a sanitized copy of `raw` safe to render on the public site (nh3 allowlist)."""
    if not raw:
        return ""
    return nh3.clean(
        raw,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes=_ALLOWED_SCHEMES,
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )


# --- CSS -------------------------------------------------------------------- #

# Substrings that must never survive in served CSS (case-insensitive).
_CSS_FORBIDDEN = re.compile(
    r"(?:@import|@charset|expression\s*\(|javascript:|vbscript:|behavior\s*:|-moz-binding"
    r"|</style|<!--|-->)",
    re.IGNORECASE,
)
# url(...) whose target is not http(s)/relative — blocks url(javascript:), url(data:...script).
_CSS_BAD_URL = re.compile(r"url\(\s*['\"]?\s*(?:javascript|vbscript|data)\s*:", re.IGNORECASE)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _scope_selector(selector: str, scope: str) -> str:
    """Prefix each comma-separated selector with the page scope so a page's CSS cannot escape
    its own container. `:root`/`html`/`body` are rewritten to the scope root, not the document."""
    parts = []
    for sel in selector.split(","):
        sel = sel.strip()
        if not sel:
            continue
        if sel in (":root", "html", "body"):
            parts.append(scope)
        else:
            parts.append(f"{scope} {sel}")
    return ", ".join(parts)


def sanitize_css(raw: str, *, scope_id: str) -> str:
    """Sanitize and scope custom CSS to `#page-{scope_id}`.

    Fails safe: if the input contains a forbidden construct we cannot neutralise, the whole
    stylesheet is rejected (returns ""), because partial stripping of hostile CSS is fragile.
    Supported: plain rules and `@media`/`@supports` blocks. Other at-rules are dropped (v1).
    """
    if not raw:
        return ""
    css = _CSS_COMMENT.sub("", raw)
    if _CSS_FORBIDDEN.search(css) or _CSS_BAD_URL.search(css):
        return ""  # fail safe — reject the whole stylesheet
    scope = f"#page-{scope_id}"
    return _scope_block(css, scope).strip()


def _scope_block(css: str, scope: str) -> str:
    """Scope every top-level rule in `css`. Recurses into @media/@supports blocks."""
    out: list[str] = []
    i = 0
    n = len(css)
    while i < n:
        brace = css.find("{", i)
        if brace == -1:
            break
        header = css[i:brace].strip()
        # Find the matching close brace for this block (handles one level of nesting).
        depth = 1
        j = brace + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        body = css[brace + 1 : j - 1]
        if header.startswith("@media") or header.startswith("@supports"):
            out.append(f"{header} {{ {_scope_block(body, scope)} }}")
        elif header.startswith("@"):
            pass  # drop other at-rules in v1 (@font-face/@keyframes/etc.)
        else:
            out.append(f"{_scope_selector(header, scope)} {{ {body.strip()} }}")
        i = j
    return " ".join(out)
