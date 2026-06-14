#!/usr/bin/env python3
"""
generate_all.py — Fetch all Notion recipes and generate a GitHub Pages site.

Usage:
  python generate_all.py
  python generate_all.py --out-dir docs
"""

import os, sys, re, json, argparse, requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from flashcard import (
    build_cards, get_title, get_plain_text, load_template,
    NOTION_HEADERS, RECIPES_DB_ID, NOTION_TOKEN,
)

SCRIPT_DIR         = os.path.dirname(os.path.abspath(__file__))
INDEX_TEMPLATE_FILE = os.path.join(SCRIPT_DIR, "index_template.html")


# ── Notion ─────────────────────────────────────────────────────────────────

def fetch_all_recipes():
    pages, cursor = [], None
    while True:
        payload = {
            "page_size": 100,
            "sorts": [{"property": "Recipe Name", "direction": "ascending"}],
        }
        if cursor:
            payload["start_cursor"] = cursor
        resp = requests.post(
            f"https://api.notion.com/v1/databases/{RECIPES_DB_ID}/query",
            headers=NOTION_HEADERS,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return pages


def get_recipe_meta(page):
    props = page["properties"]

    def sel(key):
        s = props.get(key, {}).get("select")
        return s["name"] if s else ""

    def txt(key):
        return get_plain_text(props.get(key, {}).get("rich_text", []))

    def multi(key):
        return [t["name"] for t in props.get(key, {}).get("multi_select", [])]

    return {
        "name":       get_title(page),
        "cuisine":    sel("Cuisine"),
        "time":       txt("Time to Make"),
        "difficulty": sel("Difficulty"),
        "status":     sel("Status"),
        "tags":       multi("Tags"),
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def slugify(name):
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "recipe"


def load_index_template():
    if not os.path.exists(INDEX_TEMPLATE_FILE):
        print(f"❌ Template not found: {INDEX_TEMPLATE_FILE}")
        sys.exit(1)
    with open(INDEX_TEMPLATE_FILE, encoding="utf-8") as f:
        return f.read()


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="docs", help="Output directory (default: docs)")
    args = parser.parse_args()

    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN missing in .env")
        sys.exit(1)

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    print("Fetching all recipes from Notion...")
    pages = fetch_all_recipes()
    print(f"   -> {len(pages)} recipes found\n")

    flashcard_tmpl = load_template()
    index_tmpl     = load_index_template()

    recipes_meta = []
    seen_slugs   = {}

    for idx, page in enumerate(pages, 1):
        meta = get_recipe_meta(page)
        name = meta["name"].strip()
        if not name:
            continue

        # deduplicate slugs
        base_slug = slugify(name)
        count     = seen_slugs.get(base_slug, 0) + 1
        seen_slugs[base_slug] = count
        slug = base_slug if count == 1 else f"{base_slug}-{count}"
        meta["slug"] = slug

        print(f"[{idx}/{len(pages)}] {name}")

        cards = build_cards(page)
        ing_count  = sum(1 for c in cards if c["type"] == "ingredient")
        step_count = sum(1 for c in cards if c["type"] == "step")
        print(f"         {len(cards)} cards ({ing_count} ingredients, {step_count} steps)")

        html = (flashcard_tmpl
                .replace("__RECIPE_NAME__", name)
                .replace("__TOTAL__",       str(len(cards)))
                .replace("__CARDS_JSON__",  json.dumps(cards, ensure_ascii=False)))

        with open(os.path.join(out_dir, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(html)

        recipes_meta.append(meta)

    print(f"\nGenerating index.html ({len(recipes_meta)} recipes)...")
    index_html = index_tmpl.replace(
        "__RECIPES_JSON__",
        json.dumps(recipes_meta, ensure_ascii=False),
    )
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print()
    print("=" * 50)
    print(f"OUTPUT:  {os.path.abspath(out_dir)}/")
    print(f"PAGES:   {len(recipes_meta)} recipe pages + index.html")
    print()
    print("Push docs/ to GitHub Pages to deploy.")


if __name__ == "__main__":
    main()
