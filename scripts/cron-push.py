#!/usr/bin/env python3
"""
Cron job: Push 2 new blog articles to WeChat draft box.
"""
import requests
import json
import time
import os
import re
import sys

APPID = "wx098e516e3867bd0d"
APPSECRET = "36980b93b7a4860963415a492d6255d7"
BLOG_DIR = "/Users/william/writing/src/content/blog"
COVER_DEFAULT = "/Users/william/Desktop/日常工作文稿/推广文案/公众号/封面_厦门灯塔.jpg"
COVER_FT = "/Users/william/Desktop/Daily/封面_读金融时报学英文写作.jpg"

def get_access_token():
    url = "https://api.weixin.qq.com/cgi-bin/stable_token"
    payload = {"grant_type": "client_credential", "appid": APPID, "secret": APPSECRET}
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            if "access_token" in data:
                return data["access_token"]
            print(f"Token error attempt {attempt+1}: {data}")
            if data.get("errcode") == 40164:
                print("⚠️ IP not whitelisted (40164). Aborting.")
                sys.exit(1)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"Token attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    raise RuntimeError("Failed to get access_token after 3 attempts")

def upload_cover(token, cover_path):
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
    for attempt in range(3):
        try:
            with open(cover_path, 'rb') as f:
                files = {'media': ('cover.jpg', f, 'image/jpeg')}
                result = requests.post(url, files=files, timeout=30).json()
            if "media_id" in result:
                return result["media_id"]
            print(f"Cover upload error attempt {attempt+1}: {result}")
            if result.get("errcode") == 40164:
                print("⚠️ IP not whitelisted (40164). Aborting.")
                sys.exit(1)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"Cover upload attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    return None

def truncate_to_bytes(text, limit):
    if len(text.encode('utf-8')) <= limit:
        return text
    truncated = text
    while len(truncated.encode('utf-8')) > limit - 3:
        truncated = truncated[:-1]
    return truncated + "..."

def strip_frontmatter(md_text):
    if md_text.startswith('---'):
        idx = md_text.find('---', 3)
        if idx != -1:
            return md_text[idx + 3:].lstrip('\n')
    return md_text

def remove_h1(md_text):
    lines = md_text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# ') and not stripped.startswith('## '):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)

def inline_to_html(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.*?\)', r'\1', text)
    text = re.sub(r'!\[(.*?)\]\(.*?\)', r'\1', text)
    return text

def escape_html(text):
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

def md_to_wechat_html(md_text, title=""):
    html_parts = []
    if title:
        html_parts.append(f"<h2>{escape_html(title)}</h2>")
    lines = md_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped == '---':
            html_parts.append('<hr/>')
            i += 1
            continue
        if stripped.startswith('### '):
            html_parts.append(f"<h3>{inline_to_html(stripped[4:])}</h3>")
            i += 1
            continue
        if stripped.startswith('## '):
            html_parts.append(f"<h2>{inline_to_html(stripped[3:])}</h2>")
            i += 1
            continue
        if stripped.startswith('> '):
            bq_lines = []
            while i < len(lines) and lines[i].strip().startswith('> '):
                bq_lines.append(lines[i].strip()[2:])
                i += 1
            bq_text = '<br/>'.join(inline_to_html(l) for l in bq_lines if l)
            html_parts.append(f"<blockquote>{bq_text}</blockquote>")
            continue
        if stripped.startswith('|') and stripped.endswith('|'):
            if re.match(r'^\|[\s\-:]+\|[\s\-:]', stripped):
                i += 1
                continue
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            processed = []
            for c in cells:
                c = inline_to_html(c)
                c = escape_html(c)
                processed.append(c)
            html_parts.append(f"<tr>{''.join(f'<td>{p}</td>' for p in processed)}</tr>")
            i += 1
            continue
        html_parts.append(f"<p>{inline_to_html(stripped)}</p>")
        i += 1
    return '\n'.join(html_parts)

def get_title_from_frontmatter(md_text):
    m = re.search(r'^---\s*\n\s*title:\s*"?(.+?)"?\s*\n', md_text)
    if m:
        return m.group(1).strip().strip('"')
    return None

def get_description_from_frontmatter(md_text):
    m = re.search(r'description:\s*"?(.+?)"?\s*\n', md_text)
    if m:
        return m.group(1).strip().strip('"')
    return None

def process_article(md_path, token, cover_media_id):
    slug = os.path.splitext(os.path.basename(md_path))[0]
    print(f"\n--- Processing: {slug} ---")

    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    article_title = get_title_from_frontmatter(md_text)
    if not article_title:
        print(f"  ⚠️  Cannot extract title from {slug}")
        return False

    description = get_description_from_frontmatter(md_text) or ""

    body = strip_frontmatter(md_text)
    body = remove_h1(body)

    html = md_to_wechat_html(body, title=article_title)

    # Title prefix
    if slug.startswith('ft-') or slug.startswith('ft'):
        display_title = f"读外刊学写作：{article_title}"
    else:
        display_title = article_title

    # Digest
    if description:
        digest = description[:120]
    else:
        digest = article_title[:120]

    # Truncate with conservative limits
    title_final = truncate_to_bytes(display_title, 60)
    digest_final = truncate_to_bytes(digest, 115)
    author_final = "威廉"

    print(f"  Title: {display_title}")
    print(f"  Title bytes: {len(title_final.encode('utf-8'))}/64")
    print(f"  Author: {author_final} ({len(author_final.encode('utf-8'))}/8 bytes)")
    print(f"  Digest bytes: {len(digest_final.encode('utf-8'))}/120")
    print(f"  HTML length: {len(html)} chars")

    # Push to draft
    draft_url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    article = {
        "title": title_final,
        "author": author_final,
        "digest": digest_final,
        "content": html,
        "thumb_media_id": cover_media_id,
        "content_source_url": "",
        "need_open_comment": 0,
        "only_fans_can_comment": 0
    }
    payload = {"articles": [article]}

    for attempt in range(3):
        try:
            resp = requests.post(
                draft_url,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=30
            )
            result = resp.json()
            errcode = result.get("errcode", 0)
            if errcode == 0:
                media_id = result.get("media_id", "unknown")
                print(f"  ✅ Success! media_id: {media_id}")
                return True
            elif errcode == 45003:
                title_final = truncate_to_bytes(display_title, 45)
                payload["articles"][0]["title"] = title_final
                print(f"  ⚠️  45003 - truncated title to {len(title_final.encode('utf-8'))} bytes, retrying...")
                continue
            elif errcode == 45004:
                digest_final = truncate_to_bytes(digest, 90)
                payload["articles"][0]["digest"] = digest_final
                print(f"  ⚠️  45004 - truncated digest to {len(digest_final.encode('utf-8'))} bytes, retrying...")
                continue
            else:
                print(f"  ❌ Error attempt {attempt+1}: {result}")
                if attempt < 2:
                    time.sleep(2)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  ❌ Connection error attempt {attempt+1}: {e}")
            if attempt < 2:
                time.sleep(2)

    return False


def main():
    print("=" * 60)
    print("WeChat Draft Push (Cron) - Starting")
    print("=" * 60)

    # Articles to process (2 new ones, not FT series)
    articles = [
        os.path.join(BLOG_DIR, "中考听说短文复述技巧.md"),
        os.path.join(BLOG_DIR, "中考语法填空六大考点.md"),
    ]

    # Step 1: Get access token
    print("\n[1/3] Getting access token...")
    token = get_access_token()
    print(f"  ✅ Token obtained")

    # Step 2: Upload cover image (default, non-FT)
    print("\n[2/3] Uploading cover image...")
    cover_path = COVER_DEFAULT
    print(f"  Cover: {cover_path}")
    cover_media_id = upload_cover(token, cover_path)
    if not cover_media_id:
        print("  ❌ Failed to upload cover image")
        sys.exit(1)
    print(f"  ✅ Cover uploaded, media_id: {cover_media_id}")

    # Step 3: Push articles
    print("\n[3/3] Pushing articles to draft box...")
    results = []
    for i, art in enumerate(articles, 1):
        print(f"\n--- Article {i}/{len(articles)} ---")
        r = process_article(art, token, cover_media_id)
        results.append(r)
        if i < len(articles):
            time.sleep(1.5)  # Rate limiting

    # Report
    print("\n" + "=" * 60)
    print("Results Summary:")
    for i, (art, r) in enumerate(zip(articles, results), 1):
        slug = os.path.splitext(os.path.basename(art))[0]
        status = "✅ Success" if r else "❌ Failed"
        print(f"  [{i}/2] {slug}: {status}")

    print("=" * 60)

    # Output slugs for state file update
    for art, r in zip(articles, results):
        slug = os.path.splitext(os.path.basename(art))[0]
        if r:
            print(f"SLUG_OK:{slug}")


if __name__ == "__main__":
    main()
