#!/usr/bin/env python3
"""
Convert Markdown blog content to WeChat Official Account draft HTML.

Usage:
    python scripts/md-to-wechat-html.py < input.md > output.html
    python scripts/md-to-wechat-html.py --file path/to/article.md --title "文章标题"

The script:
  - Strips YAML frontmatter (---...---)
  - Removes the first H1 heading (if any)
  - Converts to WeChat-safe HTML tags only:
    p, h2, h3, strong, em, blockquote, hr, table/tr/td/th
  - Bold: **text** → <strong>text</strong>
  - Italic: *text* → <em>text</em>
  - Inline `code` → plain text (backticks stripped)
  - Table rows (|cells|) → <tr><td>cells</td></tr>
  - Blockquotes (>) → <blockquote>
  - Horizontal rules (--- on its own line) → <hr/>
  - Lists: each item wrapped in <p> (WeChat doesn't support ul/ol well)
"""

import re
import sys
import argparse


def strip_frontmatter(md_text: str) -> str:
    """Remove YAML frontmatter between --- markers."""
    if md_text.startswith('---'):
        idx = md_text.find('---', 3)
        if idx != -1:
            return md_text[idx + 3:].lstrip('\n')
    return md_text


def remove_h1(md_text: str) -> str:
    """Remove the first # Heading line (title) since it will be added separately."""
    lines = md_text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# ') and not stripped.startswith('## '):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def md_to_wechat_html(md_text: str, title: str = "") -> str:
    """
    Convert markdown body to WeChat draft-compatible HTML.
    Supported tags: p, h2, h3, strong, em, blockquote, hr,
                     table, tr, td, th (rows only — no wrapping table tag)
    """
    html_parts = []

    if title:
        html_parts.append(f"<h2>{_escape_html(title)}</h2>")

    lines = md_text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Horizontal rule
        if stripped == '---':
            html_parts.append('<hr/>')
            i += 1
            continue

        # H3 heading
        if stripped.startswith('### '):
            html_parts.append(f"<h3>{_inline_to_html(stripped[4:])}</h3>")
            i += 1
            continue

        # H2 heading
        if stripped.startswith('## '):
            html_parts.append(f"<h2>{_inline_to_html(stripped[3:])}</h2>")
            i += 1
            continue

        # Blockquote (support multi-line blockquotes)
        if stripped.startswith('> '):
            bq_lines = []
            while i < len(lines) and lines[i].strip().startswith('> '):
                bq_lines.append(lines[i].strip()[2:])
                i += 1
            bq_text = '<br/>'.join(_inline_to_html(l) for l in bq_lines if l)
            html_parts.append(f"<blockquote>{bq_text}</blockquote>")
            continue

        # Table rows — apply _inline_to_html before _escape_html
        if stripped.startswith('|') and stripped.endswith('|'):
            if re.match(r'^\|[\s\-:]+\|[\s\-:]', stripped):
                i += 1
                continue
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            # Apply _inline_to_html first (converts **bold**, etc.), then _escape_html
            processed = []
            for c in cells:
                c = _inline_to_html(c)
                c = _escape_html(c)
                processed.append(c)
            html_parts.append(f"<tr>{''.join(f'<td>{p}</td>' for p in processed)}</tr>")
            i += 1
            continue

        # Regular paragraph
        html_parts.append(f"<p>{_inline_to_html(stripped)}</p>")
        i += 1

    return '\n'.join(html_parts)


def _inline_to_html(text: str) -> str:
    """Convert inline markdown (**bold**, *italic*, `code`) to HTML."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.*?\)', r'\1', text)
    text = re.sub(r'!\[(.*?)\]\(.*?\)', r'\1', text)
    return text


def _escape_html(text: str) -> str:
    """Escape HTML special characters, preserving inline tags from _inline_to_html."""
    text = text.replace('<strong>', '\x00STRONG\x00')
    text = text.replace('</strong>', '\x00/STRONG\x00')
    text = text.replace('<em>', '\x00EM\x00')
    text = text.replace('</em>', '\x00/EM\x00')
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace('\x00STRONG\x00', '<strong>')
    text = text.replace('\x00/STRONG\x00', '</strong>')
    text = text.replace('\x00EM\x00', '<em>')
    text = text.replace('\x00/EM\x00', '</em>')
    return text


def main():
    parser = argparse.ArgumentParser(description="Convert Markdown to WeChat draft HTML")
    parser.add_argument("--file", "-f", help="Path to markdown file")
    parser.add_argument("--title", "-t", help="Article title (prepended as h2)", default="")
    parser.add_argument("--validate", action="store_true", help="Validate byte lengths and report")
    args = parser.parse_args()

    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            md_text = f.read()
    else:
        md_text = sys.stdin.read()

    body = strip_frontmatter(md_text)
    body = remove_h1(body)

    html = md_to_wechat_html(body, title=args.title)
    sys.stdout.write(html)


if __name__ == "__main__":
    main()
