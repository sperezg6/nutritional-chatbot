#!/bin/bash
# Startup script for FastAPI streaming application with uvicorn
exec python -m uvicorn streaming_handler:app --host 0.0.0.0 --port 8080
