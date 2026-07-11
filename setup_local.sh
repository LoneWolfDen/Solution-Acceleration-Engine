#!/bin/bash
# Exit on error
set -e

echo "🚀 Setting up local Solution-Acceleration-Engine..."

# 1. Create virtual environment (The 'safe' sandbox)
python3 -m venv .venv
source .venv/bin/activate

# 2. Upgrade pip and install editable package
pip install --upgrade pip
pip install -e ".[dev]"

# 3. Initialize Database (if missing)
if [ ! -f ./data/contexta.db ]; then
    echo "Creating database..."
    mkdir -p data
    # Add your DB init command here
fi

echo "✅ Setup complete! Run 'source .venv/bin/activate' then 'reflex run'"
