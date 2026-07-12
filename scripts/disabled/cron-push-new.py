#!/usr/bin/env python3
"""
Cron job: Dynamically find new blog articles and push to WeChat draft box.
"""
import json, re, time, os, sys, subprocess
import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

APPID = os.environ["WECHAT_APPID"]
APPSECRET = os.environ["WECHAT_APPSECRET"]
BLOG_DIR = "/Users/william/writing/src/content/blog"
STATE_FILE = "/Users/william/writing/.hermes-heartbeat/draft-push-state.md"
COVER_DEFAULT = "/Users/william/Desktop/日常工作文稿/推广文案/公众号/封面_厦门灯塔.jpg"
COVER_FT = "/Users/william/Desktop/Daily/封面_读金融时报学英文写作.jpg"
BASE_DIR = "/Users/william/writing"
MAX_ARTICLES = 2

def get_pushed_slugs():
    """Read pushed slugs from state file."""
    if not os.path.exists(STATE_FILE):
        return set()
    slugs = set()
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('- '):
                slugs.add(line[2:])
    return slugs

def get_all_slugs():
    """Get all blog slugs from the blog directory."""
    slugs = set()
    for f in os.listdir(BLOG_DIR):
        if f.endswith('.md'):
            slugs.add(os.path.splitext(f)[0])
    return slugs

def update_state(slugs_pushed):
    """Update the state file with new slugs."""
    # Read existing slugs
    existing = get_pushed_slugs()
    existing.update(slugs_pushed)
    
    # Write sorted state file
    sorted_slugs = sorted(existing)
    content = "# Draft Push State\n"
    content += f"Last check: {time.strftime('%Y-%m-%d %H:%M')}\n"
    content += "Pushed slugs:\n"
    for slug in sorted_slugs:
        content += f"- {slug}\n"
    
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  ✅ State file updated with {len(slugs_pushed)} new slug(s)")

def extract_yaml_field(content, field):
    """Extract YAML field value, handling escaped quotes."""
    pattern = rf'{field}:\s*"((?:[^"\\]|\\.)*)"'
    match = re.search(pattern, content)
    if match:
        return match.group(1).replace('\\"', '"')
    return None

def get_access_token():
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
            print(f"  ⚠️ Token attempt {attempt+1}/3: {data}")
            if data.get("errcode") == 40164:
                ip = requests.get('https://api.ipify.org', timeout=5).text.strip()
                print(f"  ❌ IP not whitelisted (40164). Current IP: {ip}")
                sys.exit(1)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  ⚠️ Token attempt {attempt+1}/3 failed: {e}")
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
            print(f"  ⚠️ Cover upload attempt {attempt+1}/3: {result}")
            if result.get("errcode") == 40164:
                print("  ❌ IP not whitelisted (40164).")
                sys.exit(1)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  ⚠️ Cover upload attempt {attempt+1}/3 failed: {e}")
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

def convert_md(slug, title_arg):
    """Convert markdown file to WeChat HTML using converter script."""
    filepath = os.path.join(BLOG_DIR, f"{slug}.md")
    cmd = [
        "python3",
        os.path.join(BASE_DIR, "scripts", "md-to-wechat-html.py"),
        "--file", filepath,
        "--title", title_arg
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"  ⚠️ Converter error: {result.stderr}")
    return result.stdout.strip()

def push_article(slug, token, cover_media_id):
    """Convert, validate, and push a single article to draft."""
    print(f"\n--- Processing: {slug} ---")
    
    # Read the markdown file
    filepath = os.path.join(BLOG_DIR, f"{slug}.md")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract frontmatter fields (handling escaped quotes)
    article_title = extract_yaml_field(content, 'title')
    if not article_title:
        print(f"  ❌ Cannot extract title from {slug}")
        return False
    description = extract_yaml_field(content, 'description') or ""
    
    # Determine title prefix
    if slug.startswith('ft-'):
        display_title = f"读外刊学写作：{article_title}"
        cover_path = COVER_FT
    else:
        display_title = article_title
        cover_path = COVER_DEFAULT
    
    # Convert markdown to HTML
    print(f"  Converting markdown to HTML...")
    raw_html = convert_md(slug, article_title)
    if not raw_html:
        print(f"  ❌ Empty HTML from converter for {slug}")
        return False
    
    # Fix tables: wrap <tr> groups in <table>
    fixed_html = re.sub(
        r'(<tr><td>.*?</td></tr>\s*)+',
        lambda m: f'<table>{m.group(0).strip()}</table>\n',
        raw_html
    )
    
    # Truncate title/digest conservatively
    title_final = truncate_to_bytes(display_title, 60)
    digest = description[:120]
    digest_final = truncate_to_bytes(digest, 115)
    author_final = "威廉"
    
    print(f"  Title: '{title_final}' ({len(title_final.encode('utf-8'))}/64 bytes)")
    print(f"  Author: {author_final} ({len(author_final.encode('utf-8'))}/8 bytes)")
    print(f"  Digest: {digest_final[:60]}... ({len(digest_final.encode('utf-8'))}/120 bytes)")
    print(f"  HTML: {len(fixed_html)} chars")
    
    # Push to draft
    draft_url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
    article = {
        "title": title_final,
        "author": author_final,
        "digest": digest_final,
        "content": fixed_html,
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
                print(f"  ❌ Attempt {attempt+1}/3: {result}")
                if attempt < 2:
                    time.sleep(2)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  ❌ Connection error attempt {attempt+1}/3: {e}")
            if attempt < 2:
                time.sleep(2)
    
    return False


def main():
    print("=" * 60)
    print("WeChat Draft Push (Cron) - Starting")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Step 0: Find new articles
    print("\n[0/4] Checking for new articles...")
    pushed_slugs = get_pushed_slugs()
    all_slugs = get_all_slugs()
    new_slugs = sorted(all_slugs - pushed_slugs)
    
    if not new_slugs:
        print("  No new articles found.")
        # Update last check time
        update_state([])
        print("=" * 60)
        print("Nothing to push. State file timestamp updated.")
        return
    
    print(f"  Found {len(new_slugs)} new article(s): {', '.join(new_slugs)}")
    
    # Limit to MAX_ARTICLES per round
    to_process = new_slugs[:MAX_ARTICLES]
    remaining = new_slugs[MAX_ARTICLES:]
    print(f"  Processing {len(to_process)} article(s) this round: {', '.join(to_process)}")
    if remaining:
        print(f"  {len(remaining)} article(s) deferred to next round: {', '.join(remaining)}")
    
    # Step 1: Get access token
    print("\n[1/4] Getting access token...")
    token = get_access_token()
    print(f"  ✅ Token obtained")
    
    # Step 2: Upload cover image
    print("\n[2/4] Uploading cover image...")
    # Determine which cover to upload (check if any articles are FT series)
    is_ft = any(slug.startswith('ft-') for slug in to_process)
    
    default_media_id = None
    ft_media_id = None
    
    if is_ft:
        print(f"  Uploading FT cover...")
        ft_media_id = upload_cover(token, COVER_FT)
        if not ft_media_id:
            print("  ❌ Failed to upload FT cover image")
            sys.exit(1)
        print(f"  ✅ FT cover uploaded, media_id: {ft_media_id}")
    
    # Always upload default cover (for non-FT articles)
    non_ft_slugs = [s for s in to_process if not s.startswith('ft-')]
    if non_ft_slugs:
        print(f"  Uploading default cover...")
        default_media_id = upload_cover(token, COVER_DEFAULT)
        if not default_media_id:
            print("  ❌ Failed to upload default cover image")
            sys.exit(1)
        print(f"  ✅ Default cover uploaded, media_id: {default_media_id}")
    
    # Step 3: Push articles
    print(f"\n[3/4] Pushing {len(to_process)} article(s) to draft box...")
    results = []
    for i, slug in enumerate(to_process, 1):
        # Select appropriate cover
        if slug.startswith('ft-'):
            cover_id = ft_media_id
        else:
            cover_id = default_media_id
        
        print(f"\n--- Article {i}/{len(to_process)} ---")
        success = push_article(slug, token, cover_id)
        results.append((slug, success))
        
        if i < len(to_process):
            print("  Waiting 1.5s for rate limiting...")
            time.sleep(1.5)
    
    # Step 4: Update state file
    print("\n[4/4] Updating state file...")
    successful_slugs = [slug for slug, success in results if success]
    if successful_slugs:
        update_state(successful_slugs)
    
    # Report
    print("\n" + "=" * 60)
    print("Results Summary:")
    success_count = sum(1 for _, s in results if s)
    for slug, success in results:
        status = "✅ Success" if success else "❌ Failed"
        print(f"  {slug}: {status}")
    print(f"\nPushed {success_count}/{len(to_process)} articles to draft box.")
    if remaining:
        print(f"\n⏳ {len(remaining)} article(s) still pending for next run:")
        for s in remaining:
            print(f"  - {s}")
    print("=" * 60)


if __name__ == "__main__":
    main()
