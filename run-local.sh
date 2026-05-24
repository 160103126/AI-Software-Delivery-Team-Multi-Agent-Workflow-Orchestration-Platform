#!/bin/bash

# Simple local run script for Linux/Mac
# Starts backend and frontend in separate terminals

echo "Starting local E2E test..."
echo ""

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}Starting backend on http://127.0.0.1:8000${NC}"
cd backend/src
uvicorn ai_sdlc.api:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

sleep 3

echo -e "${GREEN}Starting frontend on http://127.0.0.1:8501${NC}"
cd ../..
streamlit run frontend/streamlit_app.py --server.port 8501 &
FRONTEND_PID=$!

echo ""
echo -e "${BLUE}Both services are running...${NC}"
echo ""
echo "Frontend: http://localhost:8501"
echo "Backend API: http://localhost:8000"
echo "Backend Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both services"
echo ""

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
