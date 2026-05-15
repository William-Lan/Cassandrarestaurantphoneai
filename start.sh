#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Cassandra Restaurant Inventory ==="

# Backend setup
cd "$ROOT/backend"
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[!] Created backend/.env — add your ANTHROPIC_API_KEY before using AI features"
fi

if [ ! -d "venv" ]; then
  echo "[*] Creating Python virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
echo "[*] Installing backend dependencies..."
pip install -q -r requirements.txt

# Frontend setup
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
  echo "[*] Installing frontend dependencies..."
  npm install
fi

# Start both
echo "[*] Starting backend on http://localhost:8000"
cd "$ROOT/backend"
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "[*] Starting frontend on http://localhost:5173"
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  App running at: http://localhost:5173"
echo "  API docs at:    http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
