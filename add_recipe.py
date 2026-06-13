#!/usr/bin/env python3
"""
add_recipe.py — Add a recipe from YouTube (or manually) into Notion.

Usage:
  python add_recipe.py <youtube_url>
  python add_recipe.py manual
"""

import os
import sys
import re
import json
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
NOTION_TOKEN    = os.getenv("NOTION_TOKEN")

RECIPES_DB_ID = "46de3e3285b54299988600e344cb5904"
PANTRY_DB_ID  = "f9a201c74cb54bd3b388bf2b9fdfe2ff"

NOTION_HEADERS = lambda: {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


# ── URL detection ──────────────────────────────────────────────────────────

def is_instagram_url(url):
    return "instagram.com" in url


# ── YouTube ────────────────────────────────────────────────────────────────

def extract_video_id(url):
    match = re.search(r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


def fetch_youtube_details(video_id):
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet", "id": video_id, "key": YOUTUBE_API_KEY},
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise ValueError(f"No video found for ID: {video_id}")
    snippet = items[0]["snippet"]
    return {
        "title":       snippet["title"],
        "description": snippet.get("description", ""),
        "channel":     snippet["channelTitle"],
    }


def fetch_top_comments(video_id, max_results=15):
    """Fetch top/pinned comments — recipe often pinned by uploader."""
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={
                "part":       "snippet",
                "videoId":    video_id,
                "order":      "relevance",  # surfaces pinned comments first
                "maxResults": max_results,
                "key":        YOUTUBE_API_KEY,
            },
        )
        resp.raise_for_status()
        comments = []
        for item in resp.json().get("items", []):
            text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            comments.append(text)
        return comments
    except Exception:
        return []  # comments disabled or API error — not fatal


# ── Instagram ──────────────────────────────────────────────────────────────

def extract_shortcode(url):
    match = re.search(r'/(?:reel|p|tv)/([A-Za-z0-9_-]+)', url)
    return match.group(1) if match else None


def fetch_instagram_details(url):
    import instaloader
    shortcode = extract_shortcode(url)
    if not shortcode:
        raise ValueError(f"Could not extract shortcode from URL: {url}")

    loader = instaloader.Instaloader()
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        caption = post.caption or ""

        comments = []
        try:
            for i, comment in enumerate(post.get_comments()):
                comments.append(comment.text)
                if i >= 14:
                    break
        except Exception:
            pass

        return {
            "title":    caption[:80] or "Instagram Recipe",
            "description": caption,
            "channel":  post.owner_username,
            "comments": comments,
        }
    except instaloader.exceptions.LoginRequiredException:
        raise RuntimeError(
            "Instagram requires login for this post.\n"
            "Run: python add_recipe.py manual\n"
            "and paste the caption manually."
        )


# ── Groq ───────────────────────────────────────────────────────────────────

def extract_recipe_with_groq(title, description, comments=None):
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)

    comments_text = ""
    if comments:
        comments_text = "\n\nTop Comments (check for pinned recipe):\n" + "\n---\n".join(comments[:10])

    prompt = f"""You are a recipe extraction assistant.

Extract recipe data from the YouTube video below and return ONLY a JSON object — no markdown, no explanation.
Check the description first, then comments if description lacks recipe details.

Video Title: {title}
Description:
{description[:3000]}{comments_text[:2000]}

Return this exact JSON structure:
{{
  "recipe_name": "clean short recipe name",
  "cuisine": "one of: Indian, Italian, Continental, Fusion, Other",
  "time_to_make": "e.g. 20 mins or 1 hour",
  "difficulty": "one of: Easy, Medium, Hard",
  "ingredients": [
    {{"name": "ingredient name", "quantity": "amount with unit", "group": "group label e.g. BASE / TEMPERING / SAUCE / FINISH"}}
  ],
  "process": "Step by step method. Each step on its own line starting with 1. 2. 3. etc.",
  "tags": ["pick any that apply: quick, one-pot, vegetarian, breakfast, lunch, dinner, snack"]
}}

If description lacks recipe details, infer what you can from the title. Keep ingredients and process minimal but accurate."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    text = response.choices[0].message.content.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text, strict=False)


# ── Notion helpers ─────────────────────────────────────────────────────────

def _rich_text(content):
    # Notion rich_text max 2000 chars per block — chunk if needed
    chunks = [content[i:i+1999] for i in range(0, len(content), 1999)]
    return [{"text": {"content": chunk}} for chunk in chunks]


def format_ingredients(ingredients):
    groups = {}
    for ing in ingredients:
        group = ing.get("group", "INGREDIENTS").upper()
        groups.setdefault(group, [])
        qty  = ing.get("quantity", "").strip()
        name = ing.get("name", "").strip()
        line = f"• {qty} {name}".strip() if qty else f"• {name}"
        groups[group].append(line)

    lines = []
    for group, items in groups.items():
        lines.append(group)
        lines.extend(items)
        lines.append("")
    return "\n".join(lines).strip()


def create_notion_recipe(recipe, source_url):
    ingredients_text = format_ingredients(recipe.get("ingredients", []))
    process_text     = recipe.get("process", "")
    tags             = recipe.get("tags", [])

    properties = {
        "Recipe Name": {"title": [{"text": {"content": recipe["recipe_name"]}}]},
        "Source URL":  {"url": source_url},
        "Cuisine":     {"select": {"name": recipe.get("cuisine", "Other")}},
        "Time to Make":{"rich_text": _rich_text(recipe.get("time_to_make", ""))},
        "Difficulty":  {"select": {"name": recipe.get("difficulty", "Easy")}},
        "Status":      {"select": {"name": "Want to Try"}},
        "Ingredients": {"rich_text": _rich_text(ingredients_text)},
        "Process":     {"rich_text": _rich_text(process_text)},
    }
    if tags:
        properties["Tags"] = {"multi_select": [{"name": t} for t in tags]}

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS(),
        json={"parent": {"database_id": RECIPES_DB_ID}, "properties": properties},
    )
    resp.raise_for_status()
    return resp.json()


def get_pantry_items():
    items, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        resp = requests.post(
            f"https://api.notion.com/v1/databases/{PANTRY_DB_ID}/query",
            headers=NOTION_HEADERS(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        for page in data["results"]:
            props    = page["properties"]
            title    = props.get("Ingredient", {}).get("title", [])
            name     = title[0]["plain_text"] if title else ""
            in_stock = props.get("In Stock", {}).get("checkbox", False)
            items.append({"id": page["id"], "name": name, "in_stock": in_stock})
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return items


def flag_need_to_buy(page_id):
    requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=NOTION_HEADERS(),
        json={"properties": {"Need to Buy": {"checkbox": True}}},
    ).raise_for_status()


def add_to_pantry(name):
    """Add new ingredient to pantry with Need to Buy flagged."""
    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS(),
        json={
            "parent": {"database_id": PANTRY_DB_ID},
            "properties": {
                "Ingredient":  {"title": [{"text": {"content": name}}]},
                "In Stock":    {"checkbox": False},
                "Need to Buy": {"checkbox": True},
            },
        },
    )
    resp.raise_for_status()


def match_pantry(recipe_ingredients, pantry_items):
    index = {item["name"].lower(): item for item in pantry_items}
    missing, have = [], []

    for ing in recipe_ingredients:
        ing_name = ing.get("name", "").lower()
        matched  = None
        for key, item in index.items():
            if ing_name in key or key in ing_name:
                matched = item
                break
        if matched:
            if matched["in_stock"]:
                have.append(ing["name"])
            else:
                missing.append((ing["name"], matched["id"]))
        else:
            missing.append((ing["name"], None))

    return missing, have


# ── Main ───────────────────────────────────────────────────────────────────

def check_env():
    missing = [v for v in ("YOUTUBE_API_KEY", "GROQ_API_KEY", "NOTION_TOKEN") if not os.getenv(v)]
    if missing:
        print(f"❌ Missing in .env: {', '.join(missing)}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python add_recipe.py <youtube_url>")
        print("  python add_recipe.py manual")
        sys.exit(1)

    check_env()
    arg = sys.argv[1]

    comments = []

    if arg.lower() == "manual":
        title       = input("Recipe name: ").strip()
        description = input("Paste description / ingredients (Enter to skip): ").strip()
        source_url  = input("Source URL (YouTube / Instagram): ").strip()

    elif is_instagram_url(arg):
        source_url = arg
        print("[1/4] Fetching Instagram post...")
        try:
            details     = fetch_instagram_details(source_url)
            title       = details["title"]
            description = details["description"]
            comments    = details["comments"]
            print(f"   -> @{details['channel']} | {len(comments)} comments fetched")
        except RuntimeError as e:
            print(f"\n[ERROR] {e}")
            sys.exit(1)

    else:
        source_url = arg
        video_id   = extract_video_id(source_url)
        if not video_id:
            print("[ERROR] Could not extract video ID from URL.")
            sys.exit(1)
        print("[1/4] Fetching video details + comments...")
        details     = fetch_youtube_details(video_id)
        title       = details["title"]
        description = details["description"]
        comments    = fetch_top_comments(video_id)
        print(f"   -> {title} ({details['channel']}) | {len(comments)} comments fetched")

    print("[2/4] Extracting recipe with Groq...")
    recipe = extract_recipe_with_groq(title, description, comments or None)
    print(f"   -> {recipe['recipe_name']} | {recipe.get('time_to_make','?')} | {recipe.get('difficulty','?')}")

    print("[3/4] Saving to Notion...")
    page     = create_notion_recipe(recipe, source_url)
    page_url = page.get("url", "")
    print(f"   -> Saved")

    print("[4/4] Checking pantry...")
    pantry          = get_pantry_items()
    missing, have   = match_pantry(recipe.get("ingredients", []), pantry)

    flagged, added = 0, 0
    for name, pid in missing:
        if pid:
            flag_need_to_buy(pid)
            flagged += 1
        else:
            add_to_pantry(name)
            added += 1

    print()
    print("=" * 50)
    print(f"RECIPE:  {recipe['recipe_name']}")
    print(f"TIME:    {recipe.get('time_to_make','?')}  |  DIFFICULTY: {recipe.get('difficulty','?')}")
    if have:
        print(f"\nHAVE ({len(have)}):  {', '.join(have)}")
    if missing:
        names = [m[0] for m in missing]
        print(f"\nNEED ({len(missing)}):  {', '.join(names)}")
        if flagged:
            print(f"  -> {flagged} item(s) flagged in Pantry")
        if added:
            print(f"  -> {added} new item(s) added to Pantry")
    else:
        print("\nYou have all ingredients!")
    print(f"\nLink: {page_url}")


if __name__ == "__main__":
    main()
