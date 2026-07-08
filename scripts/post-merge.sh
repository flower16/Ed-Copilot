#!/bin/bash
set -e

echo "--- Ed-Copilot post-merge setup ---"

if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt --quiet --no-input
fi

echo "--- Post-merge setup complete ---"
