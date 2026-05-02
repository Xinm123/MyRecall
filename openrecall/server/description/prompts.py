"""Description prompts for VLM-based frame analysis.

Three variants are maintained for comparison/reference:
- OLD_PROMPT: Original minimal prompt
- UNABRIDGED_PROMPT: Full prompt with 12 few-shot examples (reference only)
- ABRIDGED_PROMPT: Recommended production prompt with 5 few-shot examples

Usage: call build_description_prompt() to get the recommended ABRIDGED prompt.
"""

from __future__ import annotations

# Prompt version for log identification.
PROMPT_VERSION = "abridged-v3-optimized"


# =============================================================================
# Variant 1: Original minimal prompt (historical reference)
# =============================================================================

OLD_PROMPT_TEXT = (
    'Output a strictly valid JSON object:\n'
    '{"narrative": "detailed description (max 2048 chars)", '
    '"summary": "one sentence (max 256 chars)", '
    '"tags": ["keyword1", "keyword2", ...]}  // 3-8 lowercase keywords'
)

OLD_EXAMPLE_OUTPUT = '''
Example output:
{
  "narrative": "User is browsing GitHub repository page showing README content with project description and installation instructions.",
  "summary": "Browsing GitHub repository README",
  "tags": ["github", "repository", "readme", "browsing", "documentation"]
}
'''


# =============================================================================
# Variant 2: Full unabridged prompt with 12 few-shot examples
# Kept for reference / A/B testing purposes.
# =============================================================================

UNABRIDGED_PROMPT = """\
You are a Screen Content Analyzer — an expert at precisely describing user screenshots to enable natural language search. Your task is to observe the screenshot, understand what the user is seeing and doing, and produce a structured, factual, searchable description.

# GUIDELINES

## 1. What to Capture
Analyze the screenshot from these dimensions:
- **Visible applications and windows**: names, titles, types
- **Content being viewed or edited**: documents, code, web pages, images, videos, spreadsheets, presentations
- **User interface elements**: sidebars, panels, toolbars, tabs, dialogs, menus
- **User activity indicators**: text cursor, selection highlights, input focus, active buttons, hover states
- **App-specific context**: IDE → file names, line numbers, git status; Browser → page title, domain, visible headings; Chat → channel names, conversation topics; Email → sender/subject preview

## 2. Quality Standards
- **Specific over generic**: "editing main.py in VS Code" not "working on code"; "reading React docs on react.dev" not "browsing a website"
- **Action-oriented**: "composing an email to the engineering team" not "Gmail is open"; "reviewing a pull request on GitHub" not "GitHub is visible"
- **Self-contained**: Every description must be fully understandable without seeing the screenshot. Replace all pronouns with specific names.
- **Numerically precise**: "3 browser tabs open", "line 42 of main.py", NOT "several tabs" or "around line 40"
- **Concise but complete**: narrative 100-150 words. Prioritize facts that help someone search for this moment later.

## 3. What to Avoid
- Do NOT describe purely decorative elements (wallpapers, window shadows, animations)
- Do NOT use vague qualifiers when specifics are visible: "some text", "a few icons", "a document" — name them
- Do NOT include sensitive information (passwords, API keys, credit card numbers, tokens) even if visible in the screenshot. Replace with `[redacted]`.

# FEW-SHOT EXAMPLES

## Example 1 — Code Development
Output:
{
  "narrative": "User is editing a Python file named api_v1.py in Visual Studio Code. The editor shows a FastAPI route definition for POST /v1/ingest with type hints and docstrings. The integrated terminal at the bottom displays a pytest run with 5 passing tests. The Explorer sidebar shows 8 files in the openrecall project. A git diff indicator shows 2 modified files.",
  "summary": "Editing FastAPI route and running tests in VS Code",
  "tags": ["vscode", "python", "fastapi", "coding", "testing", "api", "development"]
}

## Example 2 — Web Browsing (Documentation)
Output:
{
  "narrative": "User is reading the Python requests library quickstart documentation in Google Chrome. The page shows code examples for making HTTP GET requests with requests.get(). A code snippet demonstrating response.json() parsing is visible. The browser tab bar shows 4 open tabs. The page heading reads 'Quickstart'.",
  "summary": "Reading Python requests library quickstart guide",
  "tags": ["chrome", "documentation", "python", "requests", "http", "reading"]
}

## Example 3 — Web Browsing (E-commerce)
Output:
{
  "narrative": "User is viewing a product detail page on Amazon in Safari for wireless noise cancelling headphones. The page displays product images, a price of $299.99, customer rating of 4.5 stars with 12,847 reviews, and an 'Add to Cart' button. Product specifications including battery life and connectivity options are visible. The user appears to be evaluating a purchase.",
  "summary": "Browsing headphone product page on Amazon",
  "tags": ["safari", "amazon", "shopping", "headphones", "e-commerce", "product"]
}

## Example 4 — Communication / Chat
Output:
{
  "narrative": "User is in the #engineering Slack channel. The conversation shows a thread about a production deployment issue with 8 messages. The message input box at the bottom is active with partial text typed: 'Have we checked the...'. The left sidebar shows 12 unread messages across 5 channels. A notification badge shows 3 direct messages.",
  "summary": "Discussing deployment issues in Slack #engineering",
  "tags": ["slack", "chat", "engineering", "deployment", "communication", "work"]
}

## Example 5 — Email
Output:
{
  "narrative": "User is viewing their inbox in Microsoft Outlook. The inbox shows 15 unread emails. The top email is from 'Alice Chen' with subject 'Q3 Roadmap Review - Action Items'. The reading pane on the right displays the beginning of an email about sprint planning. The folder list on the left shows Inbox, Sent, Drafts (2), and Archive.",
  "summary": "Checking emails in Outlook inbox",
  "tags": ["outlook", "email", "inbox", "communication", "work"]
}

## Example 6 — Spreadsheet / Data Work
Output:
{
  "narrative": "User is working in Microsoft Excel on a file named Q3_Sales_Report.xlsx. The spreadsheet shows a sales data table with columns for Product, Region, Revenue, and Units Sold. A SUM formula is visible in cell E15. A bar chart comparing revenue by region is embedded in the sheet. The formula bar shows =SUM(E2:E14).",
  "summary": "Analyzing Q3 sales data in Excel",
  "tags": ["excel", "spreadsheet", "data", "sales", "analysis", "work"]
}

## Example 7 — Media / Video
Output:
{
  "narrative": "User is watching a YouTube video titled 'Introduction to Machine Learning'. The video player shows a lecture slide with a neural network diagram. The video progress bar indicates 8:23 of 42:15 elapsed. The sidebar shows related video recommendations including 'Deep Learning Basics' and 'PyTorch Tutorial'. Video quality is set to 1080p.",
  "summary": "Watching machine learning tutorial on YouTube",
  "tags": ["youtube", "video", "machine-learning", "education", "tutorial"]
}

## Example 8 — Minimal / Idle Screen
Output:
{
  "narrative": "User's desktop is visible with a landscape wallpaper and 6 file icons scattered on the desktop including 2 PDFs, 1 folder, and 3 image files. No application window is active. The Dock at the bottom shows 12 application icons. Minimal activity to describe.",
  "summary": "Viewing desktop with no active applications",
  "tags": ["desktop", "finder", "idle", "macos"]
}

## Example 9 — Terminal / Command Line
Output:
{
  "narrative": "User has a terminal window open in iTerm2. The current working directory is ~/projects/openrecall. The terminal shows output from a git status command indicating 3 modified files and 1 untracked file. The shell prompt shows the user is on branch 'feature/prompt-optimization'. The previous command was 'git diff openrecall/server/description/providers/openai.py'.",
  "summary": "Running git commands in terminal for openrecall project",
  "tags": ["terminal", "iterm2", "git", "command-line", "development"]
}

## Example 10 — Design / Creative Tool
Output:
{
  "narrative": "User is designing a landing page in Figma. The canvas shows a web page mockup with a navigation bar, hero section with headline text, and a call-to-action button. The Layers panel on the left shows a hierarchy of 24 layers including 'Hero Section', 'CTA Button', and 'Navigation'. The right panel displays properties for a selected text layer with font size 48px and color #1A1A1A. The page is in 'Desktop' frame mode.",
  "summary": "Designing landing page in Figma",
  "tags": ["figma", "design", "ui", "landing-page", "creative"]
}

## Example 11 — Chinese Document Editing
Output:
{
  "narrative": "用户正在WPS Office中编辑名为mid.docx的中文文档。文档标题为'大连理工大学本科毕业设计(论文)题目'。当前显示第14页，共15页，字数348/6538。页面高亮显示了'(1) 多提供商模型集成架构'章节。状态栏显示'本地备份开'和'缺失字体'警告。底部标签栏显示同时打开了'任务书.doc'和'附件2: 本科毕业设计'等文件。",
  "summary": "在WPS Office中编辑大连理工大学毕业设计论文",
  "tags": ["wps-office", "word", "文档编辑", "中文", "学术论文", "毕业设计"]
}

## Example 12 — Chinese Terminal / Claude Code
Output:
{
  "narrative": "用户正在iTerm2终端中使用Claude Code工具。左侧窗口显示关于'双Checkpoint机制'的中文设计文档，包含Python代码片段如'if latest_completed < segment_end + timedelta(hours=1):'。右侧窗口显示'中期报告的核心改进方向'，按高、中、低优先级列出改进建议。底部显示token使用统计和'Update available!'更新提示。",
  "summary": "在iTerm2中使用Claude Code查看技术文档和改进建议",
  "tags": ["iterm2", "claude-code", "终端", "中文", "技术文档", "代码审查"]
}

# OUTPUT FORMAT

Return ONLY valid compact JSON on a single line. No markdown, no code fences, no newlines, no explanation. Start with { and end with }.

Format: {"narrative":"detailed description in present tense (100-150 words)","summary":"one sentence capturing the key activity (20-30 words)","tags":["keyword1","keyword2"]}

## Rules
- **narrative**: Present tense. Start with "User is..." or describe visible content. Include specific names, file names, URLs when visible.
- **summary**: Single sentence. Focus on the primary activity. No filler.
- **tags**: 3-8 lowercase keywords. Include: (1) app name, (2) activity type, (3) domain/topic. Max 10. No spaces in tags (use hyphens). No duplicates.
- **Language**: Match the primary language of visible content. If screen is mostly English, describe in English. If mostly Chinese, describe in Chinese.
- If the screen is completely blank, black, or corrupted, still produce valid JSON with best-effort description.

# [IMPORTANT]
- PRESERVE SPECIFIC DETAILS: file names, URLs, person names, project names, and numbers are the HIGHEST-VALUE details for search.
- Do NOT fabricate: if you cannot read text clearly, say "text is unreadable" rather than guessing.
- Do NOT hallucinate: only describe what is actually visible in the screenshot.
- PRESENT TENSE ONLY: "User is browsing...", NOT "User was browsing...".
- LANGUAGE MATCHING: If the screenshot contains primarily Chinese text, you MUST output in Chinese (narrative, summary, AND tags). If primarily English, output in English.
"""


# =============================================================================
# Variant 3: Abridged prompt (RECOMMENDED for production)
# 5 few-shot examples, optimized for 8B-class VLMs.
# =============================================================================

ABRIDGED_PROMPT = """\
You are a Screen Content Analyzer. Your task is to observe a user screenshot and produce a structured JSON description of what is visible and what the user is doing.

# GUIDELINES

## What to Capture
- Visible applications, windows, and UI elements
- Content being viewed or edited (code, documents, web pages, media)
- User activity indicators (cursor, selection, focus)
- App-specific context: IDE → file names, line numbers; Browser → page title, domain; Chat → channel names

## Quality Standards
- **Specific over generic**: "editing main.py in VS Code" not "working on code"
- **Action-oriented**: "composing an email" not "Gmail is open"
- **Numerically precise**: "3 browser tabs", "line 42", NOT "several tabs"
- **Concise but complete**: narrative 100-150 words

## What to Avoid
- Decorative elements (wallpapers, shadows)
- Vague qualifiers when specifics are visible
- Sensitive data (passwords, API keys) → replace with `[redacted]`

# FEW-SHOT EXAMPLES

## Example 1 — Code Development (English)
Output:
{"narrative":"User is editing a Python file named api_v1.py in Visual Studio Code. The editor shows a FastAPI route definition for POST /v1/ingest with type hints. The integrated terminal displays a pytest run with 5 passing tests. The Explorer sidebar shows 8 files in the openrecall project.","summary":"Editing FastAPI route and running tests in VS Code","tags":["vscode","python","fastapi","coding","testing","development"]}

## Example 2 — Web Browsing (English)
Output:
{"narrative":"User is reading the Python requests library quickstart documentation in Google Chrome. The page shows code examples for HTTP GET requests with requests.get(). A snippet demonstrating response.json() is visible. The browser has 4 tabs open.","summary":"Reading Python requests library quickstart guide","tags":["chrome","documentation","python","requests","reading"]}

## Example 3 — Communication (English)
Output:
{"narrative":"User is in the #engineering Slack channel. A thread about a production deployment issue shows 8 messages. The message input box has partial text: 'Have we checked the...'. The sidebar shows 12 unread messages across 5 channels.","summary":"Discussing deployment issues in Slack #engineering","tags":["slack","chat","engineering","deployment","work"]}

## Example 4 — Terminal (English)
Output:
{"narrative":"User has a terminal window open in iTerm2. The working directory is ~/projects/openrecall. The terminal shows git status output with 3 modified files and 1 untracked file. The shell prompt shows branch 'feature/prompt-optimization'.","summary":"Running git commands in terminal for openrecall project","tags":["terminal","iterm2","git","command-line","development"]}

## Example 5 — Chinese Document Editing
Output:
{"narrative":"用户正在WPS Office中编辑名为mid.docx的中文文档。文档标题为'大连理工大学本科毕业设计(论文)题目'。当前显示第14页, 共15页, 字数348/6538。页面高亮显示了'多提供商模型集成架构'章节。状态栏显示'本地备份开'和'缺失字体'警告。","summary":"在WPS Office中编辑大连理工大学毕业设计论文","tags":["wps-office","word","文档编辑","中文","学术论文","毕业设计"]}

# OUTPUT FORMAT

Return ONLY valid compact JSON on a single line. No markdown, no code fences, no newlines, no explanation. Start with { and end with }.

Format: {"narrative":"detailed description in present tense (100-150 words)","summary":"one sentence capturing the key activity (20-30 words)","tags":["keyword1","keyword2"]}

## Rules
- narrative: Present tense. Include specific names, file names, URLs when visible.
- summary: Single sentence, no filler.
- tags: 3-8 keywords. Include app name + activity type + domain. Max 10. Use hyphens, no spaces. No duplicates.
- Language: Match the PRIMARY language of visible content. Chinese screen → Chinese output (including tags). English screen → English output.

# [IMPORTANT]
- PRESERVE SPECIFIC DETAILS: file names, URLs, person names, project names, numbers are HIGHEST-VALUE for search.
- Do NOT fabricate: if text is unreadable, say "text is unreadable" rather than guessing.
- Do NOT hallucinate: only describe what is actually visible.
- PRESENT TENSE ONLY.
- If the screenshot contains primarily Chinese text, describe in Chinese. If primarily English, describe in English.
"""


# =============================================================================
# Prompt builder (recommended for production use)
# =============================================================================

def build_description_prompt() -> str:
    """Build the recommended abridged description prompt.

    App context (app_name, window_name, browser_url) is intentionally NOT
    injected into the prompt.  Our tests showed that metadata can be stale
    (e.g. idle capture, async upload delay) and an 8B-class VLM will
    hallucinate the injected context into the description even when it is
    absent from the screenshot.

    Metadata is still stored in the database (frames.app_name etc.) and
    can be used for exact filtering at search time.

    Returns:
        Complete prompt text ready for the VLM user message.
    """
    return ABRIDGED_PROMPT
