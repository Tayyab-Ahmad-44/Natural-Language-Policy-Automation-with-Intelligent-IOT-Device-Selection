.PHONY: run run-frontend run-backend frontend backend

run:
	@echo "Choose a target: make run-frontend or make run-backend"

run-frontend:
	cd frontend && npm run dev

run-backend:
	cd backend && uvicorn application:app --reload --host 0.0.0.0 --port 8000

frontend: run-frontend

backend: run-backend
