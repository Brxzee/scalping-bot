#!/bin/bash
# Run from repo root (scalping_bot) to create git repo and prepare for push.
set -e
cd "$(dirname "$0")/.."

if [ -d .git ]; then
  echo "Repository already initialized."
else
  git init
  echo "Git repository initialized."
fi

git add .
git status

if ! git diff --cached --quiet 2>/dev/null; then
  git commit -m "Initial commit: Powell ICT scalping detector

- Config (YAML + env), data fetcher (yfinance/ccxt), real-time monitor
- Structure: swing, FVG, order block, liquidity sweep, ATR
- Wick theory (50% midpoint, respect), ICT rejection block
- Killzone filter (London/NY), confluence engine, setup output
- Telegram notifier integration, run_detector CLI, tests"
  echo "Initial commit created."
else
  echo "Nothing to commit (or already committed)."
fi

echo ""
echo "To push to GitHub:"
echo "  1. Create a new repository on GitHub (no README/license)."
echo "  2. Run:"
echo "     git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
echo "     git branch -M main"
echo "     git push -u origin main"
echo ""
echo "Or with SSH:"
echo "     git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git"
echo "     git branch -M main"
echo "     git push -u origin main"
