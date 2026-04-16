# Skill Registry — trading-bot

Generated: 2026-04-16

## Project Context

- **Stack**: Python 3.11+, python-telegram-bot 21.x, OpenAI GPT-4o, yfinance, asyncio
- **Architecture**: Single-process async Telegram bot, polling mode
- **Testing**: None configured

## User Skills

| Skill | Trigger |
|-------|---------|
| branch-pr | When creating a pull request, opening a PR, or preparing changes for review |
| issue-creation | When creating a GitHub issue, reporting a bug, or requesting a feature |
| judgment-day | When user says "judgment day", "adversarial review", "dual review", or "juzgar" |
| skill-creator | When user asks to create a new skill or document patterns for AI |

> Note: `go-testing` excluded — Go-specific, not applicable to this Python project.

## Convention Files

- `CLAUDE.md` — project instructions, architecture notes, deployment details
- `README.md` — stack overview, setup instructions, roadmap

## Compact Rules

### branch-pr
Trigger: creating PR, opening PR, preparing changes for review.
- Follow issue-first enforcement: link PR to an existing issue
- Use conventional commits in PR title
- Include summary, test plan, and risk section in PR body

### issue-creation
Trigger: creating GitHub issue, reporting bug, requesting feature.
- Use issue-first enforcement: always create issue before starting work
- Label bugs as `bug`, features as `enhancement`
- Include reproduction steps for bugs; acceptance criteria for features

### judgment-day
Trigger: "judgment day", "adversarial review", "dual review", "juzgar".
- Launch two independent blind judge sub-agents in parallel
- Synthesize findings; apply fixes; re-judge until both pass or escalate after 2 iterations

### skill-creator
Trigger: create new skill, add agent instructions, document patterns for AI.
- Follow Agent Skills spec
- Include frontmatter with name, description, trigger
- Keep skills focused on a single concern
