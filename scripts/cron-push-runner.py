#!/usr/bin/env python3
"""
Push new blog articles to WeChat Official Account draft box.
Handles markdown→HTML conversion, cover upload, draft push, state update.
"""
import json
import os
import re
import sys
import time
import traceback

from dotenv import load_dotenv

# ============================================================
# CONFIG — load from env for security
# ============================================================
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
APPID = os.environ["WECHAT_APPID"]
APPSECRET = os.environ["WECHAT_APPSECRET"]
BLOG_DIR = "/Users/william/writing/src/content/blog"
STATE_FILE = "/Users/william/writing/.hermes-heartbeat/draft-push-state.md"
DEFAULT_COVER = "/Users/william/Desktop/日常工作文稿/推广文案/公众号/封面_厦门灯塔.jpg"
FT_COVER = "/Users/william/Desktop/Daily/封面_读金融时报学英文写作.jpg"

MAX_TITLE_BYTES = 60  # leave some margin vs. 64
MAX_DIGEST_BYTES = 115  # leave some margin vs. 120


# ============================================================
# BYTE LENGTH HELPERS
# ============================================================
def byte_len(s):
    return len(s.encode("utf-8"))


def truncate_to_bytes(text, limit):
    while len(text.encode("utf-8")) > limit - 3:
        text = text[:-1]
    return text + "..."


def shorten_title_aggressive(title, limit=45):
    """Aggressively shorten title for WeChat."""
    while len(title.encode("utf-8")) > limit - 3:
        title = title[:-1]
    return title + "..."


# ============================================================
# MARKDOWN → WECHAT HTML (inlined from md-to-wechat-html.py)
# ============================================================
def strip_frontmatter(md_text):
    if md_text.startswith("---"):
        idx = md_text.find("---", 3)
        if idx != -1:
            return md_text[idx + 3 :].lstrip("\n")
    return md_text


def remove_h1(md_text):
    lines = md_text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _inline_to_html(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"!\[(.*?)\]\(.*?\)", r"\1", text)
    return text


def _escape_html(text):
    text = text.replace("<strong>", "\x00STRONG\x00")
    text = text.replace("</strong>", "\x00/STRONG\x00")
    text = text.replace("<em>", "\x00EM\x00")
    text = text.replace("</em>", "\x00/EM\x00")
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("\x00STRONG\x00", "<strong>")
    text = text.replace("\x00/STRONG\x00", "</strong>")
    text = text.replace("\x00EM\x00", "<em>")
    text = text.replace("\x00/EM\x00", "</em>")
    return text


def md_to_wechat_html(md_text, title=""):
    """Convert markdown to WeChat draft-compatible HTML."""
    html_parts = []

    if title:
        html_parts.append(f"<h2>{_escape_html(_inline_to_html(title))}</h2>")

    lines = md_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Horizontal rule
        if stripped == "---":
            html_parts.append("<hr/>")
            i += 1
            continue

        # H3 heading
        if stripped.startswith("### "):
            html_parts.append(f"<h3>{_inline_to_html(stripped[4:])}</h3>")
            i += 1
            continue

        # H2 heading
        if stripped.startswith("## "):
            html_parts.append(f"<h2>{_inline_to_html(stripped[3:])}</h2>")
            i += 1
            continue

        # Blockquote
        if stripped.startswith("> "):
            bq_lines = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                bq_lines.append(lines[i].strip()[2:])
                i += 1
            bq_text = "<br/>".join(_inline_to_html(l) for l in bq_lines if l)
            html_parts.append(f"<blockquote>{bq_text}</blockquote>")
            continue

        # Table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[\s\-:]+\|[\s\-:]", stripped):
                i += 1
                continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            processed = []
            for c in cells:
                c = _inline_to_html(c)
                c = _escape_html(c)
                processed.append(c)
            html_parts.append(
                f"<tr>{''.join(f'<td>{p}</td>' for p in processed)}</tr>"
            )
            i += 1
            continue

        # Regular paragraph
        html_parts.append(f"<p>{_inline_to_html(stripped)}</p>")
        i += 1

    raw_html = "\n".join(html_parts)

    # Wrap table rows in <table> tag
    raw_html = re.sub(
        r"(<tr><td>.*?</td></tr>\s*)+",
        lambda m: f"<table>{m.group(0).strip()}</table>\n",
        raw_html,
        flags=re.DOTALL,
    )

    return raw_html


def extract_frontmatter_field(content, field):
    """Extract YAML field value, handling escaped quotes."""
    pattern = rf'{field}:\s*"((?:[^"\\]|\\.)*)"'
    match = re.search(pattern, content)
    if match:
        return match.group(1).replace('\\"', '"')
    return None


# ============================================================
# WECHAT API HELPERS (with retry)
# ============================================================
def get_access_token():
    """Get stable access_token with retry."""
    url = "https://api.weixin.qq.com/cgi-bin/stable_token"
    payload = {
        "grant_type": "client_credential",
        "appid": APPID,
        "secret": APPSECRET,
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            if "access_token" in data:
                return data["access_token"]
            print(f"  Token error (attempt {attempt+1}): {data}")
            if "errcode" in data and data["errcode"] == 40164:
                print("  IP not whitelisted (40164). Aborting.")
                return None
            time.sleep(2)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  Token request attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2)
    return None


def upload_cover(token, cover_path):
    """Upload cover image, return media_id."""
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
    for attempt in range(3):
        try:
            with open(cover_path, "rb") as f:
                files = {"media": ("cover.jpg", f, "image/jpeg")}
                result = requests.post(url, files=files, timeout=30).json()
            if "media_id" in result:
                return result["media_id"]
            print(f"  Cover upload error (attempt {attempt+1}): {result}")
            time.sleep(2)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  Cover upload attempt {attempt+1}/3: {e}")
            if attempt < 2:
                time.sleep(2)
    return None


def push_draft(token, title, author, digest, html_content, media_id):
    """Push article to draft box with retry + truncation."""
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    article = {
        "title": title,
        "author": author,
        "digest": digest,
        "content": html_content,
        "thumb_media_id": media_id,
        "content_source_url": "",
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }

    for attempt in range(3):
        try:
            payload = {"articles": [article]}
            resp = requests.post(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=30,
            )
            data = resp.json()
            errcode = data.get("errcode", 0)

            if errcode == 0 and "media_id" in data:
                return data["media_id"]

            if errcode == 45003:
                # Title too long - truncate more
                new_title = shorten_title_aggressive(article["title"], 40)
                print(f"  Title too long ({byte_len(article['title'])} bytes). Truncating to '{new_title}' ({byte_len(new_title)} bytes)")
                article["title"] = new_title
                continue

            if errcode == 45004:
                # Digest too long - truncate more
                new_digest = truncate_to_bytes(article["digest"], 100)
                print(f"  Digest too long ({byte_len(article['digest'])} bytes). Truncating.")
                article["digest"] = new_digest
                continue

            print(f"  Draft push error: {data}")
            return None

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, ConnectionResetError) as e:
            print(f"  Draft push attempt {attempt+1}/3: {e}")
            if attempt < 2:
                time.sleep(2)
    return None


# ============================================================
# STATE FILE HELPERS
# ============================================================
def load_state():
    """Return set of pushed slugs."""
    if not os.path.exists(STATE_FILE):
        return set()
    pushed = set()
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("- "):
                pushed.add(line[2:].strip())
    return pushed


def update_state(slugs_to_add):
    """Add slugs to state file."""
    pushed = load_state()
    pushed.update(slugs_to_add)

    lines = ["# Draft Push State", f"Last check: {time.strftime('%Y-%m-%d %H:%M')}", "Pushed slugs:"]
    for s in sorted(pushed):
        lines.append(f"- {s}")

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  State file updated with {len(slugs_to_add)} new slug(s)")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"=== WeChat Draft Push: {time.strftime('%Y-%m-%d %H:%M')} ===")

    # 1. Find unpushed articles
    blog_files = [f for f in os.listdir(BLOG_DIR) if f.endswith(".md")]
    pushed_slugs = load_state()

    unpushed = []
    for fname in blog_files:
        slug = fname[:-3]  # remove .md
        if slug not in pushed_slugs:
            unpushed.append((slug, os.path.join(BLOG_DIR, fname)))

    if not unpushed:
        print("No new articles to push.")
        return

    print(f"Found {len(unpushed)} unpushed article(s).")
    for s, _ in unpushed:
        print(f"  - {s}")

    # Limit to 2 per round
    to_push = unpushed[:2]
    if len(unpushed) > 2:
        print(f"Processing first 2 (limit per round). {len(unpushed) - 2} remaining for next run.")

    # 2. Get access_token
    print("\n[Step 1/3] Getting access_token...")
    token = get_access_token()
    if not token:
        print("FAILED: Could not get access_token. Aborting.")
        return
    print(f"  Token acquired: {token[:10]}...")

    # Also check IP for whitelist debugging
    try:
        ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
        print(f"  Server IP: {ip}")
    except Exception:
        print("  Could not detect server IP.")

    # 3. Upload cover (reuse for both non-FT articles)
    print("\n[Step 2/3] Uploading cover image...")
    media_id = upload_cover(token, DEFAULT_COVER)
    if not media_id:
        print("FAILED: Could not upload cover image. Aborting.")
        return
    print(f"  Cover media_id: {media_id}")

    # 4. Process each article
    print("\n[Step 3/3] Pushing drafts...")
    success_count = 0
    newly_pushed_slugs = []

    for idx, (slug, filepath) in enumerate(to_push, 1):
        print(f"\n  [{idx}/{len(to_push)}] Processing: {slug}")

        # Read file content
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract frontmatter
        title = extract_frontmatter_field(content, "title")
        description = extract_frontmatter_field(content, "description")
        if not title:
            print(f"  SKIPPED: No title in frontmatter")
            continue

        print(f"    Raw title: {title[:50]}... ({byte_len(title)} bytes)")
        print(f"    Raw digest: {description[:40]}... ({byte_len(description) if description else 0} bytes)")

        # Truncate title/digest if needed
        if byte_len(title) > MAX_TITLE_BYTES:
            title = truncate_to_bytes(title, MAX_TITLE_BYTES)
            print(f"    Title truncated to: {title} ({byte_len(title)} bytes)")

        if description and byte_len(description) > MAX_DIGEST_BYTES:
            description = truncate_to_bytes(description, MAX_DIGEST_BYTES)
            print(f"    Digest truncated ({byte_len(description)} bytes)")

        digest = description or title[:40]

        # Convert markdown to HTML
        body = strip_frontmatter(content)
        body = remove_h1(body)
        html_content = md_to_wechat_html(body, title=title)

        # Push to draft
        author = "威廉"
        result = push_draft(token, title, author, digest, html_content, media_id)

        if result:
            print(f"  ✅ SUCCESS: {slug} (media_id: {result})")
            success_count += 1
            newly_pushed_slugs.append(slug)
        else:
            print(f"  ❌ FAILED: {slug}")

        # Rate limit delay between articles
        if idx < len(to_push):
            time.sleep(2)

    # 5. Update state
    if newly_pushed_slugs:
        update_state(newly_pushed_slugs)

    print(f"\n=== Done: Pushed {success_count}/{len(to_push)} articles ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
