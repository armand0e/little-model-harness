---
name: research
description: Research a topic on the web and summarize or write up findings
---
You are now doing web research with the web_search and fetch tools.

Workflow:
1. `web_search("your query")` — returns numbered results with titles, URLs, and snippets. Reword and search again if the results miss the point.
2. Pick the 2-4 most promising URLs and fetch each one. Prefer official sources, documentation, and well-known publications.
3. Extract only the facts relevant to the user's question. Note the source URL for each fact.
4. Answer with a short synthesis, then a "Sources:" list of the URLs you actually used.

Rules:
- Pages are truncated to ~6000 chars. If a page seems cut off before the useful part, try a more specific page/URL instead of refetching the same one.
- Never invent URLs or facts. If the pages don't answer the question, say what you found and what's missing.
- 5 fetches maximum per request — pick well rather than fetching widely.
- If the user wants the findings as a document or spreadsheet, load that skill after the research is done.
