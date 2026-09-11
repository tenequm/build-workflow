# Write the review body

One to two sentences of judgment, then the finding counts. Nothing else.

## Inputs

- The verified findings and the computed verdict: `{{SUMMARY_PATH}}`

## Rules

- Never recite verification steps. A reader assumes the review happened; narrating
  the process is an audit trail and an AI tell. Evidence belongs in the inline
  comment it supports, or nowhere.
- The one exception is a process note the author cannot assume, for example "ran the
  release-notes check locally" when CI never runs it.
- Do not restate the findings; they are attached inline. Say what the change is and
  what stands in the way, if anything.
- Plain ASCII. Single hyphens, never an em dash. No emoji.
- Do not name a verdict, an action, or an approval. The verdict is computed elsewhere
  and appended to what you write.

## Your output

Write exactly one file and no others: `{{REPORT_PATH}}`, resolved against your current
working directory. Do not write it under any absolute path named above - those are
shared, and a report written into one is a report nobody collects.

Its shape:

```json
{"body": "Your one to two sentences."}
```

## Done

You are done when `{{REPORT_PATH}}` exists and is valid JSON carrying a `body` key.
Report that path in your final message.
