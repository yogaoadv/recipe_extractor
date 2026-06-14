#!/usr/bin/env python3
"""
flashcard.py — Generate a phone-friendly cooking flashcard from a Notion recipe.

Usage:
  python flashcard.py "Recipe Name"
  python flashcard.py "Recipe Name" --out docs/index.html
"""

import os, sys, re, json, argparse, requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

NOTION_TOKEN  = os.getenv("NOTION_TOKEN")
RECIPES_DB_ID = "46de3e3285b54299988600e344cb5904"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


# ── Notion fetch ───────────────────────────────────────────────────────────

def search_recipe(name):
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{RECIPES_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={"filter": {"property": "Recipe Name", "title": {"contains": name}}},
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"No recipe found matching: '{name}'")
    if len(results) > 1:
        names = [get_title(r) for r in results]
        print(f"Multiple matches: {', '.join(names)}")
        print(f"Using first: {names[0]}")
    return results[0]


def get_title(page):
    t = page["properties"].get("Recipe Name", {}).get("title", [])
    return "".join(b.get("plain_text", "") for b in t)


def get_plain_text(rich_text_list):
    return "".join(b.get("plain_text", "") for b in rich_text_list)


# ── Card parsing ───────────────────────────────────────────────────────────

def parse_ingredients(text):
    cards = []
    current_group = "INGREDIENTS"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # ALL-CAPS group header (no bullet, no leading digit)
        if re.match(r'^[A-Z][A-Z\s/&]+$', line) and not line.startswith('•'):
            current_group = line
        elif line.startswith('•') or line.startswith('-'):
            text_clean = re.sub(r'^[•\-]\s*', '', line).strip()
            if text_clean:
                cards.append({"type": "ingredient", "group": current_group, "text": text_clean})
        else:
            # ingredient without bullet prefix
            if line:
                cards.append({"type": "ingredient", "group": current_group, "text": line})
    return cards


def parse_steps(text):
    cards = []
    current_num = None
    current_lines = []

    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r'^(\d+)[.)]\s*(.*)', line)
        if m:
            if current_num is not None:
                cards.append({"type": "step", "step": current_num, "text": " ".join(current_lines).strip()})
            current_num = int(m.group(1))
            current_lines = [m.group(2)] if m.group(2) else []
        elif current_num is not None and line:
            current_lines.append(line)

    if current_num is not None:
        cards.append({"type": "step", "step": current_num, "text": " ".join(current_lines).strip()})

    return cards


def build_cards(page):
    props = page["properties"]

    def txt(key):
        return get_plain_text(props.get(key, {}).get("rich_text", []))

    def sel(key):
        s = props.get(key, {}).get("select")
        return s["name"] if s else ""

    name = get_title(page)

    source_url = props.get("Source URL", {}).get("url", "") or ""

    cards = [{"type": "intro", "recipe_name": name,
               "cuisine": sel("Cuisine"), "time": txt("Time to Make"),
               "difficulty": sel("Difficulty"), "source_url": source_url}]

    ing_cards = parse_ingredients(txt("Ingredients"))
    if ing_cards:
        cards.append({
            "type":  "ingredients_all",
            "items": [{"group": c["group"], "text": c["text"]} for c in ing_cards],
        })

    step_cards = parse_steps(txt("Process"))
    if step_cards:
        cards.append({"type": "section", "label": "METHOD", "count": len(step_cards)})
        cards.extend(step_cards)

    cards.append({"type": "done", "recipe_name": name})
    return cards


# ── HTML template ──────────────────────────────────────────────────────────

TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "flashcard_template.html")

def load_template():
    if not os.path.exists(TEMPLATE_FILE):
        print(f"❌ Template not found: {TEMPLATE_FILE}")
        sys.exit(1)
    with open(TEMPLATE_FILE, encoding="utf-8") as f:
        return f.read()


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", help="Recipe name (partial match)")
    parser.add_argument("--out", default="flashcard.html", help="Output HTML file path")
    args = parser.parse_args()

    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN missing in .env")
        sys.exit(1)

    print(f"[1/3] Searching Notion for '{args.recipe}'...")
    page = search_recipe(args.recipe)
    name = get_title(page)
    print(f"   -> Found: {name}")

    print("[2/3] Building cards...")
    cards = build_cards(page)
    ing_count  = sum(1 for c in cards if c["type"] == "ingredient")
    step_count = sum(1 for c in cards if c["type"] == "step")
    print(f"   -> {len(cards)} cards ({ing_count} ingredients, {step_count} steps)")

    print(f"[3/3] Writing {args.out}...")
    os.makedirs(os.path.dirname(args.out), exist_ok=True) if os.path.dirname(args.out) else None

    html = (load_template()
            .replace("__RECIPE_NAME__", name)
            .replace("__TOTAL__", str(len(cards)))
            .replace("__CARDS_JSON__", json.dumps(cards, ensure_ascii=False)))

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print()
    print("=" * 50)
    print(f"RECIPE:  {name}")
    print(f"CARDS:   {len(cards)} total")
    print(f"OUTPUT:  {args.out}")
    print()
    print("Open in browser or push to GitHub Pages.")


if __name__ == "__main__":
    main()
