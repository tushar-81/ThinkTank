from pydantic import BaseModel, Field
from langchain_core.tools import tool
from typing import List, Optional
from backend.Agents.Common_State import State
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from backend.Agents.Search_Agent import search, get_webpage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from backend.render_charts import inject_charts, image_to_base64,inject_page_break_css, html_to_pdf, inject_font_html, inject_background
import base64
import os

load_dotenv()


@tool
def search_tool(query: str):
    """
    PURPOSE:
    Fetch external web information.

    WHEN TO USE:
    When external data or validation is needed.

    WHEN NOT TO USE:
    Do not invoke for conceptual synthesis, creative tasks, or queries where the training data provides sufficient context.

    INPUT:
    query (str): Specific search query.

    OUTPUT:
    dict: Relevant results with sources and snippets.

    USAGE:
    Extract key facts and integrate into insights.
    """
    search_dict=search(query=query)
    web_search_result=get_webpage(query, search_dict)

    return web_search_result


class DataPoint(BaseModel):
    label: str = Field(description="Category or segment name.")
    value: float = Field(description="Numerical value representing the category.")


class Visualization(BaseModel):
    type: str = Field(description="Type of visualization: pie_chart, bar_chart, line_chart, or table.")
    title: str = Field(description="Title of the visualization.")


class Insight(BaseModel):
    text: str = Field(description="Concise statement of the key insight.")
    importance: str = Field(description="Priority level of the insight: low, medium, or high.")
    supporting_points: Optional[List[str]] = Field(
        description="Short supporting points or reasoning behind the insight.")
    data_points: Optional[List[DataPoint]] = Field(
        description="Structured data used for visualization, if applicable.")
    visualization: Optional[Visualization] = Field(
        description="Suggested visualization for this insight, if useful.")
    chart_path: Optional[str] = None 


class Agent1Output(BaseModel):
    Business_insights: List[Insight] = Field(
        description="Insights related to business model, value proposition, and viability.")
    Market_insights:List[Insight] = Field(
        description="Insights about market demand, trends, competitors, and opportunities.")
    Technical_insights: List[Insight] = Field(
        description="Insights on technology choices, feasibility, and constraints.")
    Risks: List[Insight] = Field(
        description="Potential risks, challenges, or uncertainties identified.")
    Action_items: List[Insight] = Field(
        description="Concrete next steps or tasks derived from the discussion.")
    Decisions: List[Insight] = Field(
        description="Decisions or conclusions agreed upon by the team.")
    Open_questions: List[Insight] = Field(
        description="Unresolved questions requiring further discussion or research.")
    Customer_insights: List[Insight] = Field(
        description="Insights about user needs, pain points, and behavior.")
    Rival_companies : List[Insight] = Field(
        description='Rival companies who have a similar product in the market')
    Monetization_strategies: List[Insight] = Field(
        description="Proposed revenue models or pricing strategies.")
    Growth_strategies: List[Insight] = Field(
        description="Ideas for scaling, marketing, and expansion.")
    Priority_signals: List[Insight] = Field(
        description="Key ideas that were emphasized, repeated, or strongly agreed upon.")
    Knowledge_gaps: List[Insight] = Field(
        description="Missing information or areas needing validation or research.")


def Agent1(state:State):
    conversation_history = ''
    
    messages = state['messages']
    for message in messages:
        if isinstance(message, HumanMessage):
            content=str(message.content).lower().split(' ')
            if '@AI' or '@ai' or '@Ai' in content:
                continue
            conversation_history+= f"Role : Human, Content : {message.content}\n"
        if isinstance(message, AIMessage):
            conversation_history+= f"Role : Assistant, Content : {message.content}\n"
    
    prompt = '''
You are an Advanced Project Intelligence Agent AND a Visual Report Designer.

Your output will be converted into a VISUAL PDF REPORT — not an article.
This means EVERY section must have at least one chart or visual element.
A report without charts is UNACCEPTABLE.

---

CORE MISSION:

You have two jobs:
1. Extract and generate insights that go BEYOND the team's discussion
2. Make EVERY insight visually representable with data

If the conversation does not contain numerical data — SEARCH FOR IT.
If search does not find exact numbers — DERIVE reasonable estimates based on industry standards.
A report with no charts is a FAILURE.

---

MANDATORY CHART REQUIREMENTS:

Every category MUST have at least ONE insight with:
- data_points populated (minimum 3 data points)
- visualization assigned

You MUST produce charts for:

1. Market_insights
   → ALWAYS include market size over time (line_chart)
   → Search: "[product category] market size forecast [year]"
   → Example data_points: [{label: "2023", value: 18}, {label: "2024", value: 21}, ...]

2. Rival_companies
   → ALWAYS include competitor comparison (bar_chart)
   → Compare on: AI Features, Pricing Score, Market Share, User Rating
   → Search: "[competitor] user rating" or "[competitor] pricing"
   → Example data_points: [{label: "Slack", value: 6}, {label: "Notion", value: 5}, ...]

3. Monetization_strategies
   → ALWAYS include revenue model distribution (pie_chart)
   → Search: "[product type] SaaS monetization models"
   → Example data_points: [{label: "Freemium", value: 45}, {label: "Per Seat", value: 30}, ...]

4. Risks
   → ALWAYS include risk severity comparison (bar_chart)
   → Assign severity scores (1-10) to each risk identified
   → Example data_points: [{label: "Data Privacy", value: 9}, {label: "Competition", value: 7}, ...]

5. Growth_strategies
   → ALWAYS include growth channel effectiveness (bar_chart)
   → Search: "[product type] user acquisition channels"
   → Example data_points: [{label: "Webinars", value: 35}, {label: "SEO", value: 25}, ...]

6. Customer_insights
   → ALWAYS include user segment breakdown (pie_chart)
   → Example data_points: [{label: "Startups", value: 40}, {label: "Enterprise", value: 35}, ...]

7. Technical_insights
   → ALWAYS include tech stack comparison or performance scores (bar_chart)
   → Example data_points: [{label: "React", value: 8}, {label: "Vue", value: 7}, ...]

8. Priority_signals
   → ALWAYS include priority matrix as bar_chart
   → Assign priority scores (1-10) to each signal
   → Example data_points: [{label: "AI Features", value: 9}, {label: "Security", value: 8}, ...]

9. Action_items
   → ALWAYS include effort vs impact as bar_chart
   → Assign impact scores (1-10) to each action item
   → Example data_points: [{label: "Define MVP", value: 9}, {label: "Onboarding", value: 7}, ...]

10. Business_insights
    → ALWAYS include business model viability scores (bar_chart)
    → Assign viability scores (1-10) to each strategy
    → Example data_points: [{label: "Freemium", value: 8}, {label: "Enterprise", value: 7}, ...]

---

SEARCH TOOL INSTRUCTIONS:

You MUST search for real numbers. Use search_tool for:

1. Market size and growth data
   → "[product category] market size CAGR forecast"

2. Competitor ratings and pricing
   → "[competitor name] G2 rating" or "[competitor] pricing per seat"

3. User acquisition channels effectiveness
   → "SaaS user acquisition channels effectiveness statistics"

4. Industry monetization benchmarks
   → "[product type] SaaS freemium conversion rate"

5. Tech stack performance benchmarks
   → "React vs Vue performance benchmark 2025"

Make up to 5 search calls. Always integrate findings into data_points.
If exact numbers are not found, use industry-standard estimates and mark them as approximate.

---

DATA POINT RULES:

NEVER leave data_points as None if ANY of the following is true:
- You can find numbers via search
- You can derive scores based on the discussion (e.g. importance → score)
- You can estimate based on industry standards
- You can create a comparison across 3+ items

MINIMUM 3 data points per visualization.
MAXIMUM 7 data points per visualization (keep charts readable).

Values must be:
- Actual numbers (market size in $B)
- Scores out of 10 (feature scores, risk scores, priority scores)
- Percentages (market share, distribution)
- Counts (number of features, team size)

---

VISUALIZATION ASSIGNMENT RULES:

- line_chart → time series data, trends, growth projections
- bar_chart → comparisons between items, scores, rankings
- pie_chart → proportions, distributions, market share
- table → structured multi-attribute comparison (use sparingly)

NEVER assign visualization=None if data_points are present.
NEVER leave data_points=None if a comparison or ranking is possible.

---

EXTRACTION CATEGORIES:

For EACH category generate insights regardless of whether the team discussed it.
If the team discussed it — go deeper and add what they missed.
If the team did NOT discuss it — research and generate insights anyway.
Every category must have minimum 2 insights, with at least 1 containing chart data.

Categories:
- Business_insights
- Market_insights
- Technical_insights
- Risks
- Action_items
- Decisions
- Open_questions
- Customer_insights
- Rival_companies
- Monetization_strategies
- Growth_strategies
- Priority_signals
- Knowledge_gaps

---

INSIGHT QUALITY RULES:

Each insight must be:
- Specific and grounded in real data or the conversation
- Actionable — the team can do something with it
- Non-obvious — go one layer deeper than what was said

---

OUTPUT RULES:

- Return ONLY valid JSON matching the schema
- Every category must have at least 2 insights
- AT LEAST ONE insight per category MUST have data_points and visualization
- importance: low | medium | high
- Do NOT leave any category empty
- Do NOT leave data_points=None when scores or comparisons are possible

---
'''

    human_instruction = f'''
The team is currently discussing the following project. Analyze it deeply and generate comprehensive insights across ALL categories.

CONVERSATION:
{conversation_history}

INSTRUCTIONS:
- Use search_tool to research competitors, market data, and validate technical choices
- Do NOT limit yourself to only what was discussed
- Every category must be populated — research what the team didn't cover
- Surface insights the team hasn't thought of yet
'''
    
    OPENAI_API_KEY=os.getenv('OPENAI_API_KEY')

    llm=ChatOpenAI(model='gpt-4o-mini')
    llm_with_tool=llm.bind_tools([search_tool])
    llm_structure=llm_with_tool.with_structured_output(Agent1Output)

    response=llm_structure.invoke([SystemMessage(content=prompt), HumanMessage(content=human_instruction)])

    return {
        'Agent1Output':response
    }

class Agent2Output(BaseModel):
    html: str = Field(description="Complete HTML document string for the report. Must be valid, self-contained, and ready for rendering or PDF conversion.")

import re
import base64

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


def Agent2(state : State):
    agent1_output=state['Agent1Output']

    print(type(agent1_output))  # check what type it actually is
    print(isinstance(agent1_output, dict))

    if isinstance(agent1_output, dict):
        agent1_output = Agent1Output.model_validate(agent1_output)
    elif isinstance(agent1_output, str):
        agent1_output = Agent1Output.model_validate_json(agent1_output)
        
    instruction = """
You are a Report Generation Agent.

Your task is to convert structured insights (JSON input) into a professional, visually rich HTML report.

---

COLOR SCHEME — STRICT, DO NOT DEVIATE:

Use ONLY these colors throughout the entire document:
- Primary dark green:  #1a472a  (headings, section titles, header background)
- Mid green:           #2d6a4f  (subheadings, borders, accents)
- Light green:         #52b788  (highlights, badges, bullet markers)
- Pale green:          #95d5b2  (backgrounds of cards, subtle fills)
- White:               #ffffff  (main content background)
- Dark text:           #333333  (body text)
- Muted text:          #666666  (secondary text, labels)

DO NOT use blue, purple, red, or any other color family.
ALL h1, h2, h3 tags must use color: #1a472a — never blue.

---

BACKGROUND IMAGE — CRITICAL:

The body must have this EXACT CSS:

  body {{
      background-image: BG_IMAGE_PLACEHOLDER;
      background-size: cover;
      background-repeat: no-repeat;
      background-attachment: fixed;
  }}

Also add a position:fixed full-page div as the very first element inside <body>:

  <div style="position:fixed;top:0;left:0;width:100%;height:100%;
              background-image:BG_IMAGE_PLACEHOLDER;
              background-size:cover;background-repeat:no-repeat;z-index:-1;"></div>

Keep BG_IMAGE_PLACEHOLDER exactly as written — DO NOT replace it.

---

CHART PLACEHOLDERS — MANDATORY:

For every insight that has a visualization, you MUST insert a placeholder in this EXACT format:

  <div class="chart-container">[Insert CHART_TYPE: CHART_TITLE]</div>

Where CHART_TYPE and CHART_TITLE come directly from the insight's visualization field.

Example:
  If visualization = {{"type": "bar_chart", "title": "Risk Severity Comparison"}}
  You must write: <div class="chart-container">[Insert bar_chart: Risk Severity Comparison]</div>

Rules:
- Place the placeholder IMMEDIATELY after the insight text it belongs to
- Use the EXACT title from the visualization field — do not paraphrase it
- Do NOT skip any insight that has a visualization
- Do NOT write placeholder text like "chart here" — use the exact format above

---

LAYOUT AND STYLING:

Structure:
- A dark green header (#1a472a) with white title text and the date
- Leave 80px padding at top and 220px padding at bottom (for background wave design)
- Side padding: 50px left and right
- Each section in a white semi-transparent card: background: rgba(255,255,255,0.93)
- Section headings (h2) in #1a472a with a 4px left border in #52b788
- Bullet points using color #52b788 markers
- High importance insights get a left border: border-left: 3px solid #52b788
- Medium importance insights get a left border: border-left: 3px solid #95d5b2

Chart container styling:
  .chart-container {{
      background: rgba(248, 255, 252, 0.9);
      border: 1px solid #95d5b2;
      border-radius: 8px;
      padding: 12px;
      margin: 12px 0;
  }}

---

CONTENT SECTIONS (in this order):
1. Executive Summary
2. Business Insights
3. Market Insights
4. Technical Insights
5. Risks
6. Customer Insights
7. Rival Companies
8. Monetization Strategy
9. Growth Strategy
10. Action Plan
11. Priority Signals
12. Open Questions
13. Knowledge Gaps

---

OUTPUT RULES:
- Return ONLY valid HTML starting with <!DOCTYPE html>
- DO NOT wrap in markdown code fences
- DO NOT add explanations
- DO NOT hallucinate new information
- Use BG_IMAGE_PLACEHOLDER exactly as written — never replace it

---
"""
    ai_message=f"""

INPUT JSON:
{agent1_output}
    """
    
    llm = ChatOpenAI(model='gpt-4o-mini')
    structured_llm = llm.with_structured_output(Agent2Output)
    response = structured_llm.invoke([HumanMessage(content=instruction), AIMessage(content=ai_message)])

    html = response.html

    html = re.sub(r'<link[^>]+fonts\.googleapis\.com[^>]*>', '', html)
    html = re.sub(r'@import url\([^)]*fonts[^)]*\);?', '', html)


    html = inject_charts(html, agent1_output)


    html = inject_page_break_css(html)

    image_b64 = image_to_base64('./pdf_image.png')
    html = inject_background(html, image_b64)

    html = inject_font_html(html, font_path='./Helvetica.ttf')

    html_to_pdf(html, output_path='./PDF/report.pdf')
    return {
        "pdf_html": html,
        "messages": [AIMessage(content=f"Report generated successfully at path ./PDF/report.pdf")]
    }
    