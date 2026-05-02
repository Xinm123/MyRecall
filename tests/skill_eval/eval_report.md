# Skill Evaluation Report: v1

Total cases: 12

| ID | Prompt | Score | Endpoint | Params | No Redundant | Notes |
|---|--------|-------|----------|--------|-------------|-------|
| T1 | What was I doing today?... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/activity-summary; All required params prese... |
| T2 | Which apps did I use yesterday?... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/activity-summary; All required params prese... |
| T3 | Find the PR I was reviewing... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/search; All required params present: ['q', ... |
| T4 | Did I see anything about AI?... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/search; All required params present: ['q', ... |
| T5 | Did I open GitHub today?... | 100/100 | 40 | 30 | 30 | One of expected endpoints called: ['/v1/activity-summary', '/v1/search']; All re... |
| T6 | What was I doing in frame 42?... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/frames/42/context; No required params to ch... |
| T7 | What did I code in VSCode?... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/search; All required params present: ['star... |
| T8 | How long did I spend on Safari?... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/activity-summary; All required params prese... |
| T9 | Show me a screenshot... | 100/100 | 40 | 30 | 30 | Acceptable endpoint called: ['/v1/search', '/v1/activity-summary']; No required ... |
| T10 | Show me frame 42... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/frames/42; No required params to check; No ... |
| T11 | Summarize my day... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/activity-summary; All required params prese... |
| T12 | Did I see anything about React in the la... | 100/100 | 40 | 30 | 30 | Correct primary endpoint called: /v1/search; All required params present: ['q', ... |

## Summary

- Total Score: 1200/1200
- Average: 100.0/100
