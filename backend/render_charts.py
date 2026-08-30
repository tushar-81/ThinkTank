import matplotlib
matplotlib.use('Agg')          # must be set before importing pyplot
import matplotlib.pyplot as plt # for drawing charts
import base64                   # for encoding PNG → base64 string
import re                       # for finding placeholders in HTML
from io import BytesIO          # in-memory file — no disk writing needed


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — build_chart_lookup()
#
# PURPOSE:
#   Agent1Output is a Pydantic object with 13 categories (Business_insights,
#   Market_insights, etc.). Each category is a List[Insight]. Each Insight
#   MAY have data_points and visualization attached.
#
#   This function reads all of them and builds ONE flat dictionary so we can
#   quickly find chart data by title later.
#
# INPUT:  agent1_output  →  Agent1Output (Pydantic object from state)
# OUTPUT: lookup dict    →  { "title lowercase": {type, title, labels, values} }
# ─────────────────────────────────────────────────────────────────────────────

def build_chart_lookup(agent1_output) -> dict:
    lookup = {}

    # Handle both Pydantic object and plain dict
    if isinstance(agent1_output, dict):
        categories = list(agent1_output.values())
    else:
        categories = [
            agent1_output.Business_insights,
            agent1_output.Market_insights,
            agent1_output.Technical_insights,
            agent1_output.Risks,
            agent1_output.Action_items,
            agent1_output.Decisions,
            agent1_output.Open_questions,
            agent1_output.Customer_insights,
            agent1_output.Rival_companies,
            agent1_output.Monetization_strategies,
            agent1_output.Growth_strategies,
            agent1_output.Priority_signals,
            agent1_output.Knowledge_gaps,
        ]

    for category in categories:
        if not isinstance(category, list):
            continue
        for insight in category:
            if isinstance(insight, dict):
                viz = insight.get('visualization')
                dps = insight.get('data_points')
                if viz and dps:
                    title = viz['title']
                    lookup[title.lower()] = {
                        "type"  : viz['type'],
                        "title" : title,
                        "labels": [dp['label'] for dp in dps],
                        "values": [dp['value'] for dp in dps],
                    }
            else:
                if insight.visualization and insight.data_points:
                    title = insight.visualization.title
                    lookup[title.lower()] = {
                        "type"  : insight.visualization.type,
                        "title" : title,
                        "labels": [dp.label for dp in insight.data_points],
                        "values": [dp.value for dp in insight.data_points],
                    }

    return lookup


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Chart generator functions
#
# PURPOSE:
#   Each function takes raw data (labels + values + title), draws a
#   matplotlib chart, saves it into an in-memory buffer (BytesIO),
#   encodes it as base64, and returns a data URI string.
#
#   The returned string looks like:
#   "data:image/png;base64,iVBORw0KGgoAAAANS..."
#
#   This string can go directly into an HTML <img src="..."> tag.
#   No file is ever written to disk.
#
# SHARED HELPER — fig_to_b64()
#   Every chart generator ends by calling this. It:
#   1. saves the figure into a BytesIO buffer (in-memory PNG)
#   2. closes the figure (prevents memory leaks)
#   3. encodes bytes → base64 string
#   4. prepends the data URI prefix
# ─────────────────────────────────────────────────────────────────────────────

COLORS = ['#1a472a', '#2d6a4f', '#52b788', '#95d5b2', '#b7e4c7', '#cce8d8']

def fig_to_b64(fig) -> str:
    buf = BytesIO()
    plt.savefig(
        buf,
        format='png',
        dpi=150,             # resolution — higher = sharper but larger file
        bbox_inches='tight', # crop whitespace around chart
        facecolor='white',
        edgecolor='none'
    )
    plt.close(fig)  # IMPORTANT — must close or matplotlib leaks memory
    buf.seek(0)     # rewind buffer to start before reading

    b64_string = base64.b64encode(buf.read()).decode('utf-8')
    return f"data:image/png;base64,{b64_string}"
    # returns: "data:image/png;base64,iVBORw0KGgo..."


def generate_bar_chart(labels: list, values: list, title: str) -> str:
    fig, ax = plt.subplots(figsize=(6, 3))

    bars = ax.bar(labels, values, color=COLORS[:len(labels)],
                  edgecolor='none', width=0.5)

    # Styling
    ax.set_title(title, fontsize=11, color='#1a472a', pad=10, fontweight='bold')
    ax.set_facecolor('white')
    fig.patch.set_facecolor('white')
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    for spine in ['left', 'bottom']:
        ax.spines[spine].set_color('#dddddd')
    ax.tick_params(colors='#555', labelsize=9)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

    # Value labels on top of each bar
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.1,
            str(val),
            ha='center', va='bottom', fontsize=9, color='#333'
        )

    plt.xticks(rotation=15, ha='right')
    plt.tight_layout()

    return fig_to_b64(fig)  # → base64 string


def generate_pie_chart(labels: list, values: list, title: str) -> str:
    fig, ax = plt.subplots(figsize=(7, 5))  # wider figure

    # Shorten labels that are too long
    short_labels = [l[:25] + '...' if len(l) > 25 else l for l in labels]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,           # no labels on wedges — use legend instead
        colors=COLORS[:len(values)],
        autopct='%1.0f%%',
        startangle=90,
        pctdistance=0.75,
        wedgeprops=dict(width=0.55)
    )
    for at in autotexts:
        at.set_fontsize(10)
        at.set_color('white')
        at.set_fontweight('bold')

    # Add legend below chart instead of labels on wedges
    ax.legend(
        wedges,
        short_labels,
        loc='lower center',
        bbox_to_anchor=(0.5, -0.25),
        ncol=2,
        fontsize=8,
        frameon=False
    )

    ax.set_title(title, fontsize=12, color='#1a472a', pad=15, fontweight='bold')
    fig.patch.set_facecolor('white')
    plt.tight_layout()

    return fig_to_b64(fig)

def generate_line_chart(labels: list, values: list, title: str) -> str:
    fig, ax = plt.subplots(figsize=(6, 3))

    ax.plot(labels, values,
            color='#2d6a4f', linewidth=2.5,
            marker='o', markersize=6,
            markerfacecolor='#52b788',
            markeredgecolor='white',
            markeredgewidth=1.5)

    # Shaded area under line
    ax.fill_between(labels, values, alpha=0.12, color='#52b788')

    ax.set_title(title, fontsize=11, color='#1a472a', pad=10, fontweight='bold')
    ax.set_facecolor('white')
    fig.patch.set_facecolor('white')
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    for spine in ['left', 'bottom']:
        ax.spines[spine].set_color('#dddddd')
    ax.tick_params(colors='#555', labelsize=9)

    # Data labels above each point
    for x, y in zip(labels, values):
        ax.annotate(str(y), (x, y),
                    textcoords="offset points",
                    xytext=(0, 8),
                    ha='center', fontsize=8, color='#2d6a4f')

    plt.tight_layout()

    return fig_to_b64(fig)  # → base64 string

def inject_font_html(html, font_path: str) -> str:
    with open(font_path, 'rb') as f:
        font_b64=base64.b64encode(f.read()).decode('utf-8')

    font_face = f"""
    <style>
      @font-face {{
        font-family: 'Inter';
        src: url('data:font/truetype;base64,{font_b64}');
      }}
    </style>"""

    html = html.replace("</head>", f"{font_face}</head>")
    return html


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — inject_charts()
#
# PURPOSE:
#   Agent2 generates HTML with text placeholders wherever a chart belongs:
#       <div>[Insert bar_chart: AI Feature Score by Competitor]</div>
#
#   This function:
#   1. Finds every placeholder using regex
#   2. Looks up the title in the dict from build_chart_lookup
#   3. Calls the right chart generator
#   4. Replaces the placeholder with a real <img> tag
#
# THE BRIDGE:
#   Agent1 stores   →  visualization.title = "AI Feature Score by Competitor"
#   Agent2 writes   →  [Insert bar_chart: AI Feature Score by Competitor]
#   We match them   →  both normalized to lowercase before comparison
#
# INPUT:  html           →  raw HTML string from Agent2 (with placeholders)
#         agent1_output  →  Agent1Output Pydantic object
# OUTPUT: html           →  same HTML but placeholders replaced with <img> tags
# ─────────────────────────────────────────────────────────────────────────────

def inject_charts(html: str, agent1_output) -> str:

    # Build the lookup dict from Agent1Output
    # { "title lowercase": {type, title, labels, values} }
    lookup = build_chart_lookup(agent1_output)

    # Regex pattern explanation:
    # \[          → literal [
    # Insert      → literal word
    # (\w+)       → capture group 1 = chart type e.g. "bar_chart"
    # :\s*        → colon + optional spaces
    # ([^\]]+)    → capture group 2 = everything until ] = chart title
    # \]          → literal ]
    pattern = r'\[Insert (\w+):\s*([^\]]+)\]'

    # re.sub with a function — called once per match found in the HTML
    def replace_placeholder(match):
        chart_type  = match.group(1)          # e.g. "bar_chart"
        chart_title = match.group(2).strip()  # e.g. "AI Feature Score by Competitor"

        # Look up using LOWERCASE title — case-insensitive matching
        chart_data = lookup.get(chart_title.lower())

        if not chart_data:
            # Title in HTML doesn't match any title in Agent1Output
            # This happens when Agent2 invents a title or makes a typo
            return f'<p style="color:#aaa;font-style:italic;font-size:11px;">[Chart data unavailable: {chart_title}]</p>'

        labels        = chart_data["labels"]
        values        = chart_data["values"]
        resolved_type = chart_data["type"]  # use type from Agent1, not from HTML placeholder

        # Call the right generator based on chart type
        if resolved_type == "bar_chart":
            img_src = generate_bar_chart(labels, values, chart_title)
        elif resolved_type == "pie_chart":
            img_src = generate_pie_chart(labels, values, chart_title)
        elif resolved_type == "line_chart":
            img_src = generate_line_chart(labels, values, chart_title)
        else:
            img_src = generate_bar_chart(labels, values, chart_title)  # fallback

        # img_src is now: "data:image/png;base64,iVBORw0KGgo..."
        # This gets embedded directly in the HTML — no external file needed
        return f'<img src="{img_src}" alt="{chart_title}" style="width:100%;max-width:520px;border-radius:6px;margin:8px 0;" />'

    # re.sub scans the entire HTML string, calls replace_placeholder
    # for every [Insert ...] match it finds, returns the modified HTML
    html = re.sub(pattern, replace_placeholder, html)

    return html


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Final assembly in Agent2
#
# This is how everything connects in your actual agent:
# ─────────────────────────────────────────────────────────────────────────────
import os
def image_to_base64(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].replace('.', '')  # e.g. "png", "jpg"
    with open(image_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode('utf-8')
    return f"data:image/{ext};base64,{encoded}"

import pdfkit
import shutil
import os
from typing import cast

def html_to_pdf(html: str, output_path: str = './PDF/report.pdf',
                font_path: str = './Helvetica.ttf') -> str:
    import os, tempfile, base64, shutil

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write HTML to temp file
    tmp_html = tempfile.NamedTemporaryFile(
        suffix='.html', delete=False, mode='w', encoding='utf-8'
    )
    tmp_html.write(html)
    tmp_html.close()

    # Write font CSS to temp file — reference font by ABSOLUTE path
    abs_font = os.path.abspath(font_path).replace('\\', '/')
    font_css_content = f"""
@font-face {{
    font-family: 'CustomFont';
    src: url('file:///{abs_font}') format('truetype');
}}
* {{
    font-family: 'CustomFont', Helvetica, Arial, sans-serif !important;
}}
"""
    tmp_css = tempfile.NamedTemporaryFile(
        suffix='.css', delete=False, mode='w', encoding='utf-8'
    )
    tmp_css.write(font_css_content)
    tmp_css.close()

    # Write footer background HTML
    image_b64 = image_to_base64('./pdf_image.png')
    footer_content = f"""<!DOCTYPE html><html><head><style>
body {{ margin:0; padding:0; }}
div {{ 
    width:100%; height:100px;
    background-image: url('{image_b64}');
    background-size: cover;
    background-position: bottom;
}}
</style></head><body><div></div></body></html>"""

    tmp_footer = tempfile.NamedTemporaryFile(
        suffix='.html', delete=False, mode='w', encoding='utf-8'
    )
    tmp_footer.write(footer_content)
    tmp_footer.close()

    wkhtmltopdf_path = (
        os.getenv('WKHTMLTOPDF_PATH') or
        shutil.which('wkhtmltopdf') or
        r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    )
    config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path) if wkhtmltopdf_path else None

    options = {
        'page-size'                : 'A4',
        'margin-top'               : '10mm',
        'margin-right'             : '15mm',
        'margin-bottom'            : '35mm',   # room for footer
        'margin-left'              : '15mm',
        'encoding'                 : 'UTF-8',
        'enable-local-file-access' : '',
        'load-error-handling'      : 'ignore',
        'load-media-error-handling': 'ignore',
        'user-style-sheet'         : tmp_css.name,   # font via external CSS
        'footer-html'              : tmp_footer.name, # background every page
        'footer-spacing'           : '0',
    }

    try:
        pdfkit.from_file(
            input=tmp_html.name,
            output_path=output_path,
            options=options,
            configuration=config,
        )
    finally:
        os.unlink(tmp_html.name)
        os.unlink(tmp_css.name)
        os.unlink(tmp_footer.name)

    return output_path

def inject_page_break_css(html: str) -> str:
    css = """<style>
/* Prevent charts and cards splitting across pages */
.chart-container, img, .insight-card {
    page-break-inside: avoid !important;
    break-inside:      avoid !important;
}

/* Each section heading starts cleanly — no orphaned heading at page bottom */
h2 {
    page-break-after:  avoid !important;
    break-after:       avoid !important;
}

/* Keep heading with the content that follows it */
h2 + * {
    page-break-before: avoid !important;
    break-before:      avoid !important;
}

/* Never leave fewer than 3 lines alone at page bottom */
p, li {
    orphans: 3;
    widows:  3;
}
</style>"""

    if '</head>' in html:
        html = html.replace('</head>', f'{css}\n</head>', 1)
    return html


def inject_background(html: str, image_b64: str) -> str:
    import re

    # Remove ALL background-image references — footer handles it now
    html = re.sub(r'background-image\s*:\s*BG_IMAGE_PLACEHOLDER\s*;?', '', html)
    html = re.sub(r'background-image\s*:\s*url\([^)]*\)\s*;?', '', html)

    # Remove any fixed background div the LLM or previous injection added
    html = re.sub(
        r'<div[^>]*position\s*:\s*fixed[^>]*>.*?</div>',
        '',
        html,
        flags=re.DOTALL
    )

    # DO NOT inject any new background div — the footer-html option handles it
    return html

