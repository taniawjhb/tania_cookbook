import os
import re
import fitz  # PyMuPDF
import json
from collections import defaultdict


def sanitize_title(title):
    title = os.path.splitext(title)[0]  # Remove file extensions
    title = re.sub(r"[^\w\s-]", "", title)  # Remove special characters
    title = re.sub(r"\s+", "_", title.strip())  # Replace spaces with underscores
    return title


def load_pdf(path):
    return fitz.open(path)


def get_most_likely_title(page):
    blocks = page.get_text("dict")["blocks"]
    title_candidates = []

    for block in blocks:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    size = span["size"]
                    if (
                        text
                        and len(text) < 50
                        and not any(char.isdigit() for char in text)
                        and not re.search(
                            r"\b(grams|ml|cup|tablespoon|teaspoon|oz)\b", text.lower()
                        )
                        and not re.match(
                            r"(?i)^(ingredients|method|directions|the cookery)$",
                            text.lower(),
                        )
                        and not text.endswith(".")
                    ):
                        title_candidates.append((text, size))

    return (
        sorted(title_candidates, key=lambda x: -x[1])[0][0]
        if title_candidates
        else None
    )


def detect_headings(doc):
    headings = []
    for i, page in enumerate(doc):
        title = get_most_likely_title(page)
        if title and title not in [h[0] for h in headings]:
            headings.append((title, i))
    return headings


def normalize_title(title):
    return re.sub(r"[\W_]+", "", title).lower()


def split_recipes(doc, headings, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for i, (title, start_page) in enumerate(headings):
        end_page = headings[i + 1][1] if i + 1 < len(headings) else len(doc)
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)

        safe_title = sanitize_title(title)
        out_path = os.path.join(out_dir, f"{safe_title}.pdf")
        new_doc.save(out_path)
    return f"✅ Split {len(headings)} recipes to: {out_dir}"


def generate_toc(headings, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("## Table of Contents\n\n")
        for i, (title, _) in enumerate(headings, 1):
            safe_title = sanitize_title(title)
            f.write(f"{i}. [{title}](cookbook_site/recipes/{safe_title}.html)\n")
    return f"📘 TOC written to: {out_path}"


def build_ingredient_index(doc, headings):
    index = defaultdict(set)
    for i, (title, start) in enumerate(headings):
        end = headings[i + 1][1] if i + 1 < len(headings) else len(doc)
        text = ""
        for p in range(start, end):
            text += doc[p].get_text("text")

        matches = re.findall(r"\b[a-zA-Z][a-zA-Z]+\b", text)
        for word in matches:
            word = word.lower()
            if (
                word
                not in {
                    "cup",
                    "cups",
                    "tsp",
                    "tbsp",
                    "grams",
                    "ml",
                    "oz",
                    "and",
                    "with",
                    "for",
                    "the",
                }
                and len(word) > 2
            ):
                index[word].add(title)
    return index


def save_index(index, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("## Ingredient Index\n\n")
        for ingredient in sorted(index):
            titles = ", ".join(sorted(index[ingredient]))
            f.write(f"- **{ingredient}** → {titles}\n")
    return f"🥕 Ingredient index saved to: {out_path}"


def export_to_html(doc, headings, index, html_dir):
    os.makedirs(html_dir, exist_ok=True)

    toc_path = os.path.join(html_dir, "index.html")
    with open(toc_path, "w", encoding="utf-8") as f:
        f.write("<h1>Recipe Index</h1>\n<ul>\n")
        for title, _ in headings:
            filename = sanitize_title(title) + ".html"
            f.write(f'<li><a href="{filename}">{title}</a></li>\n')
        f.write("</ul>\n")

    for i, (title, start_page) in enumerate(headings):
        end_page = headings[i + 1][1] if i + 1 < len(headings) else len(doc)
        html_filename = sanitize_title(title) + ".html"
        out_path = os.path.join(html_dir, html_filename)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"<h1>{title}</h1>\n")
            for p in range(start_page, end_page):
                f.write("<pre>\n" + doc[p].get_text("text") + "\n</pre>\n")

    index_path = os.path.join(html_dir, "ingredients.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("<h1>Ingredient Index</h1>\n<ul>\n")
        for ingredient in sorted(index):
            refs = ", ".join(index[ingredient])
            f.write(f"<li><strong>{ingredient}</strong>: {refs}</li>\n")
        f.write("</ul>\n")

    return f"🌐 HTML cookbook created at: {html_dir}"


def export_master_html_site(
    all_docs, all_headings, all_indexes, out_dir, recipe_sources
):
    os.makedirs(out_dir, exist_ok=True)
    recipes_dir = os.path.join(out_dir, "recipes")
    os.makedirs(recipes_dir, exist_ok=True)

    search_records = []

    def wrap_html(title, body, stylesheet="../style.css"):
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <link rel="stylesheet" href="{stylesheet}">
</head>
<body>
{body}
</body>
</html>"""

    for doc, headings, source in all_docs:
        for i, (title, start) in enumerate(headings):
            end = headings[i + 1][1] if i + 1 < len(headings) else len(doc)
            recipe_text = ""
            for p in range(start, end):
                recipe_text += doc[p].get_text("text")
                parsed = re.sub(
                    r"(?i)\bingredients\b",
                    "\n\n<h2>Ingredients</h2>",
                    recipe_text,
                    count=1,
                )
                parsed = re.sub(
                    r"(?i)\bmethod\b|\bdirections\b",
                    "\n\n<h2>Method</h2>",
                    parsed,
                    count=1,
                )

            html_filename = sanitize_title(title) + ".html"
            filepath = os.path.join(recipes_dir, html_filename)

            body = f"<h1>{title}</h1>\n"
            body += f"<p><em>From: {source}</em></p>\n"

            norm = normalize_title(title)
            sources = recipe_sources.get(norm, [])

            other_sources = [s for s in sources if s != source]
            if other_sources:
                body += f'<p><strong>Also found in:</strong> {", ".join(sorted(other_sources))}</p>\n'

            body += '<p><a href="../index.html">← Back to Index</a> | <a href="../ingredients.html">Ingredient Index</a></p>\n'
            # body += f"<pre>\n{recipe_text.strip()}\n</pre>\n"
            html_recipe = parsed.strip().replace("\n", "<br>")
            body += f"{html_recipe}\n"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(wrap_html(title, body))

            search_records.append(
                {
                    "title": title,
                    "source": source,
                    "url": f"recipes/{html_filename}",
                    "body": recipe_text,
                }
            )

    with open(os.path.join(recipes_dir, "search_data.js"), "w", encoding="utf-8") as f:
        f.write("window.searchData = ")
        json.dump(search_records, f, indent=2)
        f.write(";")

    toc_body = """
<h1>Master Recipe Index</h1>
<input type="text" id="searchInput" placeholder="Search recipes..." oninput="runSearch()" style="width:100%; padding:0.5em; margin-bottom:1em;">
<ul id="searchResults">\n"""
    for title, source in all_headings:
        filename = sanitize_title(title) + ".html"
        toc_body += f'<li><a href="recipes/{filename}">{title}</a> <small>({source})</small></li>\n'
    toc_body += "</ul>\n"
    toc_body += """
<script src="recipes/search_data.js"></script>
<script>
function runSearch() {
  const query = document.getElementById("searchInput").value.toLowerCase();
  const results = document.getElementById("searchResults");
  results.innerHTML = "";
  window.searchData.forEach(entry => {
    const text = (entry.title + " " + entry.body + " " + entry.source).toLowerCase();
    if (text.includes(query)) {
      const li = document.createElement("li");
      li.innerHTML = `<a href="${entry.url}">${entry.title}</a> <small>(${entry.source})</small>`;
      results.appendChild(li);
    }
  });
}
</script>
"""

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(wrap_html("Master TOC", toc_body, stylesheet="style.css"))

    # Build ingredient index
    index_body = "<h1>Master Ingredient Index</h1><ul>\n"
    for ingredient in sorted(all_indexes):
        refs = ", ".join(sorted(all_indexes[ingredient]))
        index_body += f"<li><strong>{ingredient}</strong>: {refs}</li>\n"
    index_body += "</ul>"

    with open(os.path.join(out_dir, "ingredients.html"), "w", encoding="utf-8") as f:
        f.write(wrap_html("Ingredient Index", index_body, stylesheet="style.css"))

    return f"📚 Styled HTML cookbook site with full-text search saved to: {out_dir}"
