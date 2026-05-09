import os, sys, json, requests, feedparser, re, html2text
from datetime import datetime, timezone, timedelta

# 从 GitHub Secrets 读取配置
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]
ATOM_FEEDS = os.environ["ATOM_FEEDS"].split(",")  # 用逗号分隔的Atom地址列表

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
PUSHPLUS_URL = "http://www.pushplus.plus/send"

def strip_html(text):
    clean = re.sub(r'<[^>]+>', '', text or '')
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def generate_summary(text, max_len=150):
    if not text or len(text) < 20:
        return text or ""
    prompt = (
        "你是一位资深地产行业分析师。"
        "请用简洁中文概括以下文章的核心内容，不超过150字。只输出摘要，不要引号或额外说明：\n\n"
        f"{text[:3000]}"
    )
    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 400
            },
            timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
        summary = result["choices"][0]["message"]["content"].strip().strip('"''「」')
        return summary if len(summary) > 5 else text[:max_len]
    except Exception as e:
        print(f"  ⚠️ 摘要生成失败: {e}", file=sys.stderr)
        return text[:max_len]

def push_to_pushplus(title, content):
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "markdown"
    }
    try:
        resp = requests.post(PUSHPLUS_URL, json=data, timeout=15)
        result = resp.json()
        if result.get("code") == 200:
            print("✅ 推送成功")
        else:
            print(f"❌ 推送失败: {result.get('msg')}")
    except Exception as e:
        print(f"❌ 推送异常: {e}")

def fetch_atom(feed_url):
    """拉取单个Atom源，返回文章列表（最近24小时）"""
    feed = feedparser.parse(feed_url)
    articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for entry in feed.entries:
        published_str = entry.get("published") or entry.get("updated") or ""
        if published_str:
            # 尝试解析时间
            try:
                pub_time = datetime.strptime(published_str[:19], "%Y-%m-%dT%H:%M:%S")
                pub_time = pub_time.replace(tzinfo=timezone.utc)
                if pub_time < cutoff:
                    continue
            except:
                pass
        # 提取正文
        content = entry.get("content") or entry.get("summary") or entry.get("description") or ""
        content_text = html2text.html2text(content) if content else ""
        articles.append({
            "title": entry.get("title", "无标题"),
            "link": entry.get("link", ""),
            "published": published_str,
            "source": feed.feed.get("title", "未知来源"),
            "content": content_text
        })
    return articles

def main():
    all_articles = []
    for url in ATOM_FEEDS:
        print(f"📡 抓取 {url}")
        articles = fetch_atom(url.strip())
        print(f"  获取到 {len(articles)} 篇文章")
        all_articles.extend(articles)

    if not all_articles:
        push_to_pushplus("地产AI速览 · 暂无更新", "过去24小时无新文章。")
        return

    # 生成摘要并构建推送内容
    brief_lines = []
    for art in all_articles[:10]:  # 最多推送10篇
        summary = generate_summary(art["content"])
        pub_display = art["published"][:16] if art["published"] else "未知时间"
        brief_lines.append(f"**[{art['source']}] {art['title']}**  `{pub_display}`")
        brief_lines.append(f"> {summary}")
        brief_lines.append(f"[阅读原文]({art['link']})\n")

    content = "\n".join(brief_lines)
    title = f"地产AI速览 ({datetime.now().strftime('%m-%d %H:%M')})"
    push_to_pushplus(title, content)

if __name__ == "__main__":
    main()
