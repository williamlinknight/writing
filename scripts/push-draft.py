#!/usr/bin/env python3
"""Push blog articles to WeChat draft box.
Run via: python3 scripts/push-draft.py
"""
import json, re, time, os, sys, subprocess
import requests

BASE_DIR = "/Users/william/writing"

# ==========================================
# Helper: run converter script
# ==========================================
def convert_md(slug, title_arg):
    """Convert markdown file to WeChat HTML."""
    filepath = os.path.join(BASE_DIR, "src", "content", "blog", f"{slug}.md")
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

# ==========================================
# Step 1: Read articles and convert HTML
# ==========================================
articles_config = [
    {
        'slug': '考前一个月作文冲刺黄金期',
        'title_arg': '考前一个月：英语作文提分的黄金窗口期',
    },
    {
        'slug': '英语写作不跑题三步定位法',
        'title_arg': '英语写作如何不跑题：三步定位法',
    }
]

articles_data = []

for cfg in articles_config:
    slug = cfg['slug']
    title_arg = cfg['title_arg']
    
    print(f"Converting: {slug}...")
    raw_html = convert_md(slug, title_arg)
    
    if not raw_html:
        print(f"  ❌ Empty HTML for {slug}")
        continue
    
    # Fix tables: wrap <tr> groups in <table>
    fixed_html = re.sub(
        r'(<tr><td>.*?</td></tr>\s*)+',
        lambda m: f'<table>{m.group(0).strip()}</table>\n',
        raw_html
    )
    
    # Read frontmatter for digest and title
    blog_path = os.path.join(BASE_DIR, "src", "content", "blog", f"{slug}.md")
    with open(blog_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract description from frontmatter
    desc_match = re.search(r'description:\s*"(.+?)"', content, re.DOTALL)
    desc = desc_match.group(1) if desc_match else title_arg
    
    # Extract title from frontmatter
    title_match = re.search(r'title:\s*"(.+?)"', content, re.DOTALL)
    display_title = title_match.group(1) if title_match else title_arg
    
    # Calculate byte sizes
    title_byte_len = len(display_title.encode('utf-8'))
    digest_len = len(desc.encode('utf-8'))
    
    print(f"  Slug: {slug}")
    print(f"  Title: '{display_title}' - {title_byte_len} bytes {'✅' if title_byte_len <= 64 else '⚠️'}")
    print(f"  Digest: {digest_len} bytes {'✅' if digest_len <= 120 else '⚠️'}")
    
    # Truncate title if needed
    title = display_title
    if title_byte_len > 61:
        while len(title.encode('utf-8')) > 61:
            title = title[:-1]
        title += "..."
    
    # Truncate digest if needed
    if digest_len > 117:
        while len(desc.encode('utf-8')) > 117:
            desc = desc[:-1]
        desc += "..."
    
    articles_data.append({
        'slug': slug,
        'display_title': display_title,
        'title': title,
        'digest': desc,
        'html': fixed_html,
    })
    print(f"  Final title: '{title}' ({len(title.encode('utf-8'))} bytes) ✅")
    print(f"  Final digest: {len(desc.encode('utf-8'))} bytes ✅")
    print()

if not articles_data:
    print("No articles to push. Exiting.")
    sys.exit(0)

# ==========================================
# Step 2: Get access token
# ==========================================
print("=" * 50)
print("STEP 2: Getting access token...")

token_url = "https://api.weixin.qq.com/cgi-bin/stable_token"
payload = {
    "grant_type": "client_credential",
    "appid": "wx098e516e3867bd0d",
    "secret": "WECHAT_APP_SECRET_PLACEHOLDER"
}

token = None
for attempt in range(3):
    try:
        resp = requests.post(token_url, json=payload, timeout=15)
        token_data = resp.json()
        if "access_token" in token_data:
            token = token_data["access_token"]
            print(f"  ✅ Token acquired: {token[:20]}...")
            break
        elif token_data.get("errcode") == 40164:
            ip = requests.get('https://api.ipify.org', timeout=5).text.strip()
            print(f"  ❌ IP {ip} not whitelisted! Exiting.")
            print(f"  Error: {token_data}")
            sys.exit(0)
        else:
            print(f"  ⚠️ Token attempt {attempt+1}: {token_data}")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        print(f"  ⚠️ Attempt {attempt+1}/3 failed: {e}")
        if attempt < 2:
            time.sleep(2)

if not token:
    print("  ❌ Failed to get token after 3 attempts")
    sys.exit(1)

# ==========================================
# Step 3: Upload cover image
# ==========================================
print("\n" + "=" * 50)
print("STEP 3: Uploading cover image...")

cover_path = "/Users/william/Desktop/日常工作文稿/推广文案/公众号/封面_厦门灯塔.jpg"
thumb_media_id = None

for attempt in range(3):
    try:
        upload_url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb"
        with open(cover_path, 'rb') as f:
            files = {'media': ('cover.jpg', f, 'image/jpeg')}
            cover_result = requests.post(upload_url, files=files, timeout=30).json()
        
        if "media_id" in cover_result:
            thumb_media_id = cover_result["media_id"]
            print(f"  ✅ Cover uploaded: media_id = {thumb_media_id}")
            break
        else:
            print(f"  ⚠️ Cover upload error: {cover_result}")
            if attempt < 2:
                time.sleep(2)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        print(f"  ⚠️ Attempt {attempt+1}/3 failed: {e}")
        if attempt < 2:
            time.sleep(2)

if not thumb_media_id:
    print("  ❌ Failed to upload cover after 3 attempts")
    sys.exit(1)

# ==========================================
# Step 4: Push articles
# ==========================================
print("\n" + "=" * 50)
print("STEP 4: Pushing drafts...\n")

draft_url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
push_results = []

for i, art in enumerate(articles_data, 1):
    print(f"--- Article {i}/{len(articles_data)}: {art['display_title'][:40]}... ---")
    
    success = False
    media_id = None
    error_msg = None
    
    for attempt in range(3):
        try:
            article_payload = {
                "title": art['title'],
                "author": "威廉",
                "digest": art['digest'],
                "content": art['html'],
                "thumb_media_id": thumb_media_id,
                "content_source_url": "",
                "need_open_comment": 0,
                "only_fans_can_comment": 0
            }
            
            body = {"articles": [article_payload]}
            encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
            
            resp = requests.post(
                draft_url,
                data=encoded,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=30
            )
            draft_result = resp.json()
            
            if "media_id" in draft_result:
                media_id = draft_result["media_id"]
                success = True
                print(f"  ✅ media_id: {media_id}")
                break
            elif draft_result.get("errcode") == 45003:
                print(f"  ⚠️ Title too long (45003), truncating...")
                while len(art['title'].encode('utf-8')) > 45:
                    art['title'] = art['title'][:-1]
                art['title'] += "..."
                print(f"  Retry title: '{art['title']}' ({len(art['title'].encode('utf-8'))} bytes)")
                continue
            elif draft_result.get("errcode") == 45004:
                print(f"  ⚠️ Digest too long (45004), truncating...")
                while len(art['digest'].encode('utf-8')) > 100:
                    art['digest'] = art['digest'][:-1]
                art['digest'] += "..."
                print(f"  Retry: digest now {len(art['digest'].encode('utf-8'))} bytes")
                continue
            else:
                error_msg = str(draft_result)
                print(f"  ❌ Error: {draft_result}")
                break
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, ConnectionResetError) as e:
            print(f"  ⚠️ Attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2)
    else:
        error_msg = "Max retries exceeded"
        print(f"  ❌ Failed after 3 attempts")
    
    push_results.append((art['slug'], art['display_title'], success, media_id, error_msg))
    time.sleep(2)

# ==========================================
# Step 5: Update state file
# ==========================================
print("\n" + "=" * 50)
print("STEP 5: Updating state file...")

state_path = os.path.join(BASE_DIR, ".hermes-heartbeat", "draft-push-state.md")
with open(state_path, 'r', encoding='utf-8') as f:
    state_lines = f.readlines()

now = time.strftime("%Y-%m-%d %H:%M")
new_lines = []
for line in state_lines:
    if line.startswith("Last check:"):
        new_lines.append(f"Last check: {now}\n")
    else:
        new_lines.append(line)

# Add new slugs
for slug, title, success, mid, err in push_results:
    if success:
        # Don't add if already present
        already = any(slug in l for l in new_lines)
        if not already:
            new_lines.append(f"- {slug}\n")
            print(f"  ✅ Added slug: {slug}")
        else:
            print(f"  ⚡ Slug already in state: {slug}")
    else:
        print(f"  ⚠️ Skipped adding slug (push failed): {slug}")

with open(state_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"  ✅ State file updated")

# ==========================================
# Summary
# ==========================================
print("\n" + "=" * 50)
print("FINAL SUMMARY")
print("=" * 50)
success_count = sum(1 for _, _, s, _, _ in push_results if s)
for slug, title, success, mid, err in push_results:
    if success:
        print(f"  ✅ Success: 「{title}」")
        print(f"     media_id: {mid}")
    else:
        print(f"  ❌ Failed: 「{title}」 - {err}")
print(f"\nPushed {success_count}/{len(push_results)} articles to draft box")
