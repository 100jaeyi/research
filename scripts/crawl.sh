#!/usr/bin/env bash
# Pull digest candidates from the GitHub search API. Output: TSV per query in ./out/
# Usage: scripts/crawl.sh [YYYY-MM-DD]   (defaults to today, UTC)
set -euo pipefail
TODAY="${1:-$(date -u +%F)}"
WEEK=$(date -u -d "$TODAY -7 days" +%F)
MONTH=$(date -u -d "$TODAY -30 days" +%F)
TWOWEEKS=$(date -u -d "$TODAY -14 days" +%F)
OUT="${OUT:-out}"; mkdir -p "$OUT"
AUTH=(); [ -n "${GITHUB_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $GITHUB_TOKEN")

q() { # name, query
  curl -s -G "${AUTH[@]}" https://api.github.com/search/repositories \
    --data-urlencode "q=$2" -d sort=stars -d order=desc -d per_page=20 |
  jq -r '.items[]? | [.stargazers_count, .full_name, (.language//"-"), .created_at[:10], .owner.type, ((.description//"")|.[0:140])] | @tsv' \
    > "$OUT/$1.tsv"
  echo "$1: $(wc -l < "$OUT/$1.tsv") rows"
  sleep 7   # unauthenticated search limit is 10/min
}

q new_week        "created:>$WEEK"
q new_month       "created:>$MONTH pushed:>$WEEK"
q agent_skills    "topic:agent-skills created:>$MONTH"
q skills_recent   "skill claude code created:>$TWOWEEKS"
q skills_md       "agent skills SKILL.md created:>$MONTH"
q mcp_servers     "topic:mcp-server created:>$MONTH"
q mcp_recent      "mcp server created:>$TWOWEEKS"
q agents          "topic:ai-agents created:>$MONTH"
