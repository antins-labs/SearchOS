---
name: developer-mozilla-org
description: >-
  Access skill for MDN Web Docs (developer.mozilla.org), the Mozilla
  documentation site covering web platform technologies. Use this skill to
  read structured reference documentation for a specific CSS property,
  JavaScript built-in object, or Web API interface, and to discover the
  catalog of reference pages under a top-level index such as the Web API
  index, CSS Reference, or the JavaScript Global Objects list.
metadata:
  searchos-category: access
  host: developer.mozilla.org
---

# MDN Web Docs access skill

`developer.mozilla.org` is the Mozilla Developer Network (MDN), the canonical
reference documentation for CSS, JavaScript, HTML, and Web APIs. This skill
reads HTML reference pages directly from the public site (no site API is
confirmed or required).

## Capabilities and commands

All commands run via:

```
python scripts/access.py <capability_id> --input '<JSON object>'
```

Output is a single JSON object on `stdout` with shape
`{"status": ..., "records": [...], "warnings": [...]}`.
Diagnostics go to `stderr`; `--help` works offline.

### 1. `read_document` — read a reference document page

Input: `{"path": "/docs/Web/CSS/display"}` — an MDN document URL path.

Reads one reference document page (CSS property, JavaScript built-in object,
Web API interface, etc.) and returns a single structured record with:

- `title` (string): the `h1` heading of the document.
- `summary` (string): the first descriptive paragraph after the heading /
  baseline banner, or the first paragraph of the first content section.
- `content` (string): the body text extracted from the static HTML, joined from
  main content sections (syntax, description, formal definition, examples,
  specifications narrative, etc). Client-rendered content is not included.
- `source_url` (string): the final HTTP(S) URL actually read (may differ from
  the requested path due to redirects, e.g. `/docs/Web/CSS/display` redirects
  to `/docs/Web/CSS/Reference/Properties/display`).
- `browser_compatibility` (string or null): the text of the page's static
  "Baseline" indicator banner (real rendered page content, e.g.
  "Baseline Widely available … well established …"), which summarizes browser
  support status. When no baseline banner is present, this falls back to the
  Browser Compat Data (BCD) query identifier from the compatibility table
  element (e.g. `css.properties.display`). The detailed compatibility table
  rows themselves require client-side JS and are not rendered in the static
  HTML; if neither source is present this field is `null`.
- `specifications` (array): objects `{title, url}` for each external
  specification link in the page's "Specifications" section (each `url` is an
  external canonical spec, e.g. `https://drafts.csswg.org/...`). Empty array
  when the section has no external spec links.

### 2. `list_reference_index` — list entries under a reference index page

Input: `{"section": "/docs/Web/API"}` — a top-level reference index URL path.

Lists the reference entries under a top-level index page and returns one record
per entry, each with:

- `title` (string): the entry title text.
- `source_url` (string): the absolute HTTP(S) link to the entry's documentation
  page on MDN.

This returns **titles and links only** (a directory-style index); it does not
fetch the body of each listed page. To read an entry, extract its `/docs/...`
path from `source_url` and pass it as `read_document`'s `path` input. For example,
`https://developer.mozilla.org/en-US/docs/Web/API/AbortController` becomes
`{"path": "/docs/Web/API/AbortController"}`. Do not pass the full URL.
Supported index pages include the Web
API index (`/docs/Web/API`), the CSS Reference (`/docs/Web/CSS/Reference`), and
the JavaScript Global Objects / standard built-in objects index
(`/docs/Web/JavaScript/Reference/Global_Objects`).

## Output status semantics

- `ok` — at least one record; `records` populated.
- `empty` — the source page was parsed but contained no matching records (only
  used when the source genuinely yields nothing). Exit code 0.
- `invalid_input` — `--input` is missing, not a JSON object, or a required
  field/type is wrong. `records=[]`, nonzero exit (2).
- `error` — network, HTTP (4xx/5xx), transport, or parser failure.
  `records=[]`, nonzero exit (1).

## Notes and limits

- HTTPS certificate verification is kept enabled; certificate/transport
  failures are reported as real errors, never suppressed.
- The `mdn-compat-table-lazy` compatibility table and `/?search=` results are
  rendered by client-side JavaScript. This skill reads the static HTML, so the
  compatibility **table rows** and keyword **search results** are not
  available. `browser_compatibility` returns the static Baseline summary when
  present, or falls back to the BCD query identifier; keyword search is not
  implemented.
- Redirects are followed; `source_url` reflects the final URL.
- Transient transport failures (timeouts, 429/5xx) are retried with bounded
  backoff before being reported as errors.

## Dependencies and setup

Requires Python 3.8+ with `beautifulsoup4` (see `requirements.txt`).

```
pip install -r requirements.txt
```

No browser or API key is required; the skill performs plain HTTPS requests.
