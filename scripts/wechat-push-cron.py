#!/usr/bin/env python3
"""Push new blog articles to WeChat Official Account draft box."""
import json, re, time, os, sys, subprocess
import requests

BASE_DIR = "/Users/william/writing"
COVER_DEFAULT = "/Users/william/Desktop/日常工作文稿/推广文案/公众号/封面_厦门灯塔.jpg"
COVER_FT = "/Users/william/Desktop/Daily/封面_读金融时报学英文写作.jpg"
STATE_PATH = os.path.join(BASE_DIR, ".hermes-heartbeat", "draft-push-state.md")
BLOG_DIR = os.path.join(BASE_DIR, "src", "content", "blog")

WECHAT_APPID = "wx098e516e3867bd0d"
WECHAT_APPSECRET = "WECHAT_APP_SECRET_PLACEHOLDER"

# ==========================================
# Helpers
# ==========================================
def byte_len(s):
    return len(s.encode('utf-8'))

def extract_yaml_field(content, field):
    """Extract YAML field value, handling escaped quotes."""
    pattern = rf'{field}:\s*"((?:[^"\\]|\\.)*)"'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).replace('\\"', '"')
    return None

def truncate_to_bytes(text, limit):
    while len(text.encode('utf-8')) > limit - 3:
        text = text[:-1]
    return text + "..."

def convert_md_to_html(slug, title_arg):
    """Convert markdown to WeChat HTML."""
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
        return None
    raw_html = result.stdout.strip()
    
    # Fix tables: wrap <tr> groups in <table>
    fixed_html = re.sub(
        r'(<tr><td>.*?</td></tr>\s*)+',
        lambda m: f'<table>{m.group(0).strip()}</table>\n',
        raw_html
    )
    return fixed_html

def get_access_token():
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.weixin.qq.com/cgi-bin/stable_token",
                json={"grant_type": "client_credential", "appid": WECHAT_APPID, "secret": WECHAT_APPSECRET},
                timeout=15
            )
            data = resp.json()
            if "access_token" in data:
                print(f"  ✅ Token acquired")
                return data["access_token"]
            elif data.get("errcode") == 40164:
                ip = requests.get('https://api.ipify.org', timeout=5).text.strip()
                print(f"  ❌ IP {ip} not whitelisted! Exiting.")
                print(f"  Error: {data}")
                return None
            else:
                print(f"  ⚠️ Token attempt {attempt+1}: {data}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  ⚠️ Token attempt {attempt+1}/3 failed: {e}")
            if attempt < 2: time.sleep(2)
    return None

def upload_cover(token, cover_path):
    for attempt in range(3):
        try:
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
            with open(cover_path, 'rb') as f:
                files = {'media': ('cover.jpg', f, 'image/jpeg')}
                result = requests.post(url, files=files, timeout=30).json()
            if "media_id" in result:
                print(f"  ✅ Cover uploaded: media_id = {result['media_id']}")
                return result["media_id"]
            else:
                print(f"  ⚠️ Cover upload error: {result}")
                if attempt < 2: time.sleep(2)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  ⚠️ Cover attempt {attempt+1}/3: {e}")
            if attempt < 2: time.sleep(2)
    return None

def push_draft(token, title, digest, html_content, thumb_media_id):
    article = {
        "title": title,
        "author": "威廉",
        "digest": digest,
        "content": html_content,
        "thumb_media_id": thumb_media_id,
        "content_source_url": "",
        "need_open_comment": 0,
        "only_fans_can_comment": 0
    }
    body = {"articles": [article]}
    
    for attempt in range(3):
        try:
            url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
            encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
            resp = requests.post(
                url,
                data=encoded,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=30
            )
            result = resp.json()
            
            if "media_id" in result:
                return result["media_id"], None
            elif result.get("errcode") == 45003:
                print(f"  ⚠️ Title too long (45003), truncating aggressively...")
                body["articles"][0]["title"] = truncate_to_bytes(body["articles"][0]["title"], 45)
                print(f"  Retry: title = '{body['articles'][0]['title']}' ({byte_len(body['articles'][0]['title'])} bytes)")
                continue
            elif result.get("errcode") == 45004:
                print(f"  ⚠️ Digest too long (45004), truncating...")
                body["articles"][0]["digest"] = truncate_to_bytes(body["articles"][0]["digest"], 100)
                print(f"  Retry: digest = {byte_len(body['articles'][0]['digest'])} bytes")
                continue
            else:
                return None, str(result)
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, ConnectionResetError) as e:
            print(f"  ⚠️ Push attempt {attempt+1}/3: {e}")
            if attempt < 2: time.sleep(2)
    
    return None, "Max retries exceeded"

def update_state(slugs_pushed, now_str, success_slugs):
    """Update state file with new slugs."""
    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.startswith("Last check:"):
            new_lines.append(f"Last check: {now_str}\n")
        else:
            new_lines.append(line)
    
    for slug in slugs_pushed:
        if slug in success_slugs:
            already = any(slug in l for l in new_lines)
            if not already:
                new_lines.append(f"- {slug}\n")
                print(f"  ✅ Added slug: {slug}")
            else:
                print(f"  ⚡ Slug already in state: {slug}")
        else:
            print(f"  ⚠️ Skipped slug (push failed): {slug}")
    
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"  ✅ State file updated")

# ==========================================
# Main
# ==========================================
def main():
    print("=" * 60)
    print("厦门灯塔 Blog → 微信公众号草稿箱 同步")
    print("=" * 60)
    
    # Articles to push
    articles_to_push = [
        {
            'slug': '英语长难句拆解到写作',
            'title_arg': '英语长难句拆解：从读懂到会写的进阶',
        },
        {
            'slug': '写了100篇还是没进步练习陷阱',
            'title_arg': '写了100篇作文还是没进步？你可能陷入了"练习陷阱"',
        }
    ]
    
    # Step 1: Convert and extract
    print("\n--- Step 1: Convert Markdown to HTML ---")
    articles_data = []
    for art in articles_to_push:
        slug = art['slug']
        title_arg = art['title_arg']
        print(f"\nProcessing: {slug}")
        
        # Read file for frontmatter
        blog_path = os.path.join(BLOG_DIR, f"{slug}.md")
        with open(blog_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract title and description from frontmatter (handle escaped quotes)
        title = extract_yaml_field(content, 'title') or title_arg
        desc = extract_yaml_field(content, 'description') or title_arg
        
        print(f"  Title: '{title}'")
        print(f"  Title bytes: {byte_len(title)}")
        print(f"  Digest bytes: {byte_len(desc)}")
        
        # Convert HTML
        html = convert_md_to_html(slug, title_arg)
        if not html:
            print(f"  ❌ HTML conversion failed for {slug}")
            continue
        
        # Truncate title if needed
        push_title = title
        if byte_len(push_title) > 61:
            push_title = truncate_to_bytes(push_title, 61)
        
        # Truncate digest if needed
        push_desc = desc
        if byte_len(push_desc) > 117:
            push_desc = truncate_to_bytes(push_desc, 117)
        
        print(f"  Final title: '{push_title}' ({byte_len(push_title)} bytes)")
        print(f"  Final digest: {byte_len(push_desc)} bytes")
        
        articles_data.append({
            'slug': slug,
            'display_title': title,
            'push_title': push_title,
            'push_desc': push_desc,
            'html': html,
        })
    
    if not articles_data:
        print("No articles to push.")
        return
    
    # Step 2: Get token
    print("\n--- Step 2: Get Access Token ---")
    token = get_access_token()
    if not token:
        print("❌ Failed to get access token")
        return
    
    # Step 3: Upload cover
    print("\n--- Step 3: Upload Cover Image ---")
    cover_path = COVER_DEFAULT  # Neither article is ft- series
    thumb_media_id = upload_cover(token, cover_path)
    if not thumb_media_id:
        print("❌ Failed to upload cover image")
        return
    
    # Step 4: Push drafts
    print("\n--- Step 4: Push Drafts ---")
    success_slugs = []
    all_slugs = []
    
    for i, art in enumerate(articles_data, 1):
        slug = art['slug']
        all_slugs.append(slug)
        print(f"\n[{i}/{len(articles_data)}] Pushing: {art['display_title'][:40]}...")
        
        try:
            media_id, error = push_draft(
                token,
                art['push_title'],
                art['push_desc'],
                art['html'],
                thumb_media_id
            )
            
            if media_id:
                print(f"  ✅ media_id: {media_id}")
                success_slugs.append(slug)
            else:
                print(f"  ❌ Failed: {error}")
        except Exception as e:
            print(f"  ❌ Exception: {e}")
        
        if i < len(articles_data):
            time.sleep(2)  # Rate limit between pushes
    
    # Step 5: Update state
    print("\n--- Step 5: Update State ---")
    now_str = time.strftime("%Y-%m-%d %H:%M")
    update_state(all_slugs, now_str, success_slugs)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for art in articles_data:
        if art['slug'] in success_slugs:
            print(f"  ✅ Success: 「{art['display_title']}」")
        else:
            print(f"  ❌ Failed: 「{art['display_title']}」")
    print(f"\nPushed {len(success_slugs)}/{len(articles_data)} articles to draft box")
    print("=" * 60)

if __name__ == "__main__":
    main()
