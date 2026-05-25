#!/usr/bin/env python3
"""
Cron job: Push unpushed blog articles to WeChat Official Account draft box.
Called by the scheduled cron job.
"""
import json
import os
import re
import subprocess
import sys
import time
import requests

# ── Configuration ──────────────────────────────────────────────────
BLOG_DIR = "/Users/william/writing/src/content/blog"
STATE_FILE = "/Users/william/writing/.hermes-heartbeat/draft-push-state.md"
SCRIPTS_DIR = "/Users/william/writing/scripts"
DEFAULT_COVER = "/Users/william/Desktop/日常工作文稿/推广文案/公众号/封面_厦门灯塔.jpg"
MAX_ARTICLES = 2

# Credentials
APPID = "wx098e516e3867bd0d"
APPSECRET = "36980b93b7a4860963415a492d6255d7"

# ── Helpers ────────────────────────────────────────────────────────

def byte_len(s):
    """Return UTF-8 byte length."""
    return len(s.encode('utf-8'))

def truncate_to_bytes(text, limit):
    """Truncate text to fit within limit bytes, adding '...'."""
    while len(text.encode('utf-8')) > limit - 3:
        text = text[:-1]
    return text + "..."

def extract_yaml_field(content, field):
    """Extract YAML field value, handling escaped quotes."""
    pattern = rf'{field}:\s*"((?:[^"\\]|\\.)*)"'
    match = re.search(pattern, content)
    if match:
        return match.group(1).replace('\\"', '"')
    return None

def read_state():
    """Read pushed slugs from state file."""
    if not os.path.exists(STATE_FILE):
        return set()
    pushed = set()
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('- '):
                pushed.add(line[2:].strip())
    return pushed

def update_state(pushed_slugs):
    """Write pushed slugs to state file."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        f.write("# Draft Push State\n")
        f.write(f"Last check: {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write("Pushed slugs:\n")
        for slug in sorted(pushed_slugs):
            f.write(f"- {slug}\n")
    print(f"State file updated with {len(pushed_slugs)} slugs.")

def get_access_token():
    """Get WeChat access token via stable_token endpoint with retry."""
    url = "https://api.weixin.qq.com/cgi-bin/stable_token"
    payload = {
        "grant_type": "client_credential",
        "appid": APPID,
        "secret": APPSECRET
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            if "access_token" in data:
                return data["access_token"]
            if data.get("errcode") == 40164:
                ip = requests.get('https://api.ipify.org', timeout=5).text.strip()
                print(f"ERROR 40164: IP {ip} not whitelisted. Add to WeChat backend.")
                return None
            print(f"Token attempt {attempt+1}/3 failed: {data.get('errmsg', data)}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"Token attempt {attempt+1}/3 connection error: {e}")
            if attempt < 2:
                time.sleep(2)
    return None

def upload_cover(token, cover_path):
    """Upload cover image to WeChat material library, return media_id."""
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
    for attempt in range(3):
        try:
            with open(cover_path, 'rb') as f:
                files = {'media': ('cover.jpg', f, 'image/jpeg')}
                result = requests.post(url, files=files, timeout=30).json()
            if "media_id" in result:
                return result["media_id"]
            print(f"Cover upload attempt {attempt+1}/3: {result}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"Cover upload attempt {attempt+1}/3 connection error: {e}")
            if attempt < 2:
                time.sleep(2)
    return None

def convert_to_html(md_path, title):
    """Use md-to-wechat-html.py to convert markdown to WeChat HTML."""
    converter = os.path.join(SCRIPTS_DIR, "md-to-wechat-html.py")
    if not os.path.exists(converter):
        print(f"ERROR: Converter script not found at {converter}")
        return None
    
    result = subprocess.run(
        [sys.executable, converter, "--file", md_path, "--title", title],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Converter error: {result.stderr[:500]}")
        return None
    
    raw_html = result.stdout
    
    # Fix: wrap <tr><td> groups in <table> tags
    raw_html = re.sub(
        r'(<tr><td>.*?</td></tr>\s*)+',
        lambda m: f'<table>{m.group(0).strip()}</table>\n',
        raw_html
    )
    
    return raw_html

def push_draft(token, title, author, digest, html_content, media_id, slug):
    """Push a single article to WeChat draft box with retry and truncation."""
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    
    article = {
        "title": title,
        "author": author,
        "digest": digest,
        "content": html_content,
        "thumb_media_id": media_id,
        "content_source_url": f"https://williamwriting.com/blog/{slug}/",
        "need_open_comment": 0,
        "only_fans_can_comment": 0
    }
    
    for attempt in range(3):
        try:
            payload = json.dumps({"articles": [article]}, ensure_ascii=False).encode('utf-8')
            headers = {"Content-Type": "application/json; charset=utf-8"}
            resp = requests.post(url, data=payload, headers=headers, timeout=30)
            result = resp.json()
            
            errcode = result.get("errcode", 0)
            
            if errcode == 0 and "media_id" in result:
                return result["media_id"]
            elif errcode == 45003:
                print(f"  Title too long ({byte_len(article['title'])} bytes). Truncating...")
                article["title"] = truncate_to_bytes(article["title"], 50)
                continue
            elif errcode == 45004:
                print(f"  Digest too long ({byte_len(article['digest'])} bytes). Truncating...")
                article["digest"] = truncate_to_bytes(article["digest"], 100)
                continue
            elif errcode == 40164:
                ip = requests.get('https://api.ipify.org', timeout=5).text.strip()
                print(f"ERROR 40164: IP {ip} not whitelisted.")
                return None
            else:
                print(f"  API error: {result}")
                return None
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  Push attempt {attempt+1}/3 connection error: {e}")
            if attempt < 2:
                time.sleep(2)
    
    return None


def main():
    print("=" * 60)
    print(f"厦门灯塔 Blog → WeChat Draft Push")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Step 1: Find unpushed articles
    pushed_slugs = read_state()
    print(f"\nAlready pushed: {len(pushed_slugs)} slugs")
    
    unpushed = []
    for fname in sorted(os.listdir(BLOG_DIR)):
        if not fname.endswith('.md'):
            continue
        slug = fname[:-3]  # remove .md
        if slug not in pushed_slugs:
            unpushed.append(slug)
    
    print(f"Unpushed articles: {len(unpushed)}")
    for s in unpushed:
        print(f"  - {s}")
    
    if not unpushed:
        print("\nNo new articles to push. Exiting.")
        return
    
    # Process max 2 articles
    to_push = unpushed[:MAX_ARTICLES]
    print(f"\nPushing up to {len(to_push)} articles...")
    
    # Step 2: Get access token
    print("\n[1/4] Getting access token...")
    token = get_access_token()
    if not token:
        print("FAILED: Could not get access token. Aborting.")
        return
    print(f"  Got token: {token[:10]}...")
    
    # Step 3: Upload cover image
    print("\n[2/4] Uploading cover image...")
    media_id = upload_cover(token, DEFAULT_COVER)
    if not media_id:
        print("FAILED: Could not upload cover image. Aborting.")
        return
    print(f"  Cover media_id: {media_id}")
    
    # Step 4 & 5: Convert and push each article
    print("\n[3/4] Converting and pushing articles...")
    
    results = []
    for i, slug in enumerate(to_push, 1):
        md_path = os.path.join(BLOG_DIR, f"{slug}.md")
        print(f"\n  [{i}/{len(to_push)}] Processing: {slug}")
        
        # Read frontmatter
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        title = extract_yaml_field(content, "title")
        digest = extract_yaml_field(content, "description")
        author = "威廉"
        
        if not title:
            print(f"  SKIPPED: Could not extract title from frontmatter")
            results.append(("skipped", slug, "no title"))
            continue
        if not digest:
            print(f"  WARNING: No description found, using title as digest")
            digest = title
        
        print(f"  Title: {title}")
        print(f"  Digest: {digest[:60]}...")
        print(f"  Title bytes: {byte_len(title)}, Digest bytes: {byte_len(digest)}")
        
        # Convert markdown to HTML
        html = convert_to_html(md_path, f"读外刊学写作：{title}" if slug.startswith("ft-") else title)
        if not html:
            print(f"  FAILED: HTML conversion error")
            results.append(("failed", slug, "conversion error"))
            continue
        
        print(f"  HTML length: {len(html)} chars")
        
        # Push to draft
        time.sleep(1.5)  # Rate limiting
        result_media_id = push_draft(token, title, author, digest, html, media_id, slug)
        
        if result_media_id:
            print(f"  ✅ SUCCESS: media_id={result_media_id}")
            pushed_slugs.add(slug)
            results.append(("success", slug, result_media_id))
        else:
            print(f"  ❌ FAILED after retries")
            results.append(("failed", slug, "API error"))
    
    # Step 6: Update state
    print("\n[4/4] Updating state file...")
    update_state(pushed_slugs)
    
    # Summary
    print("\n" + "=" * 60)
    print("PUSH SUMMARY")
    print("=" * 60)
    successes = [r for r in results if r[0] == "success"]
    skips = [r for r in results if r[0] == "skipped"]
    failures = [r for r in results if r[0] == "failed"]
    
    if successes:
        for r in successes:
            print(f"✅ {r[1]} (media_id: {r[2]})")
    if skips:
        for r in skips:
            print(f"⚠️  {r[1]} - {r[2]}")
    if failures:
        for r in failures:
            print(f"❌ {r[1]} - {r[2]}")
    
    print(f"\nTotal: {len(successes)} success, {len(failures)} failed, {len(skips)} skipped")
    print("Done.")


if __name__ == "__main__":
    main()
