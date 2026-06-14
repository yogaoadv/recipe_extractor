# Recipe Tracker

Save recipes from YouTube/Instagram into Notion. Generate phone-friendly flashcard pages for cooking.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

Copy `.env.example` to `.env` and fill in values:

```
YOUTUBE_API_KEY=...   # Google Cloud Console → YouTube Data API v3
GROQ_API_KEY=...      # console.groq.com
NOTION_TOKEN=...      # notion.so/my-integrations → create integration → copy secret
```

> Make sure your Notion integration has access to the **My Recipes** and **Pantry** databases (open each database in Notion → ••• → Add connections → select your integration).

---

## Saving a Recipe

### From YouTube or Shorts

```bash
python add_recipe.py https://www.youtube.com/watch?v=VIDEO_ID
```

### From Instagram Reel

```bash
python add_recipe.py https://www.instagram.com/reel/SHORTCODE/
```

> Instagram may require login. If it fails, use manual mode below.

### Manual entry

```bash
python add_recipe.py manual
```

Prompts for recipe name, description/ingredients, and source URL.

**What happens:**
1. Fetches video title + description + top comments
2. Sends to Groq (LLaMA 3.3 70B) — extracts recipe as structured data
3. Saves to Notion with ingredients grouped by category
4. Checks pantry — flags missing ingredients as "Need to Buy"

---

## Generating Flashcard Pages

### Single recipe (quick preview)

```bash
python flashcard.py "Rava Upma"
```

Outputs `flashcard.html` — open in browser. Partial name match works.

```bash
# Custom output path
python flashcard.py "Aglio e Olio" --out docs/aglio-e-olio.html
```

### Full site (all recipes)

```bash
python generate_all.py
```

Outputs to `docs/`:
- `docs/index.html` — recipe picker with search + cuisine filter
- `docs/{recipe-slug}.html` — flashcard page per recipe

---

## Flashcard Usage (on phone)

**Card order:** Recipe info → All ingredients → Step 1 → Step 2 → … → Done

| Action | What happens |
|--------|-------------|
| Swipe right | Next card |
| Swipe left | Previous card |
| Tap **Next** button | Next card |
| Tap **Back** button | Previous card |
| Scroll on ingredients card | See all ingredients |

---

## GitHub Pages (optional)

Host the flashcard site so it's accessible from your phone without running Python.

**One-time setup:**
1. Push this repo to GitHub
2. Go to repo **Settings → Pages**
3. Source: `Deploy from branch` → branch `main` → folder `/docs`
4. Save — site goes live at `https://<your-username>.github.io/<repo-name>/`

**After adding new recipes:**
```bash
python generate_all.py
git add docs/
git commit -m "regenerate recipe pages"
git push
```

Site updates in ~1 minute.

---

## Notion Databases

| Database | Purpose |
|----------|---------|
| 🍳 My Recipes | All saved recipes with ingredients, steps, notes |
| 🥫 Pantry | Ingredients you own — tracks In Stock + Need to Buy |

**Recipe fields:** Name, Source URL, Cuisine, Time to Make, Difficulty, Status, Ingredients, Process, My Notes, Tags

**Status values:** Want to Try → Tried Once → Regular → Favourite
