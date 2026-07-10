# Colors for terminal output
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[0;33m
BLUE := \033[0;34m
MAGENTA := \033[0;35m
NC := \033[0m # No Color

.PHONY: dev down aicore-down clean-aicore-api build-aicore-api clean-build-aicore-api embedding-down clean-embedding build-embedding clean-build-embedding clean-cache clean-novol

dev:
	@echo "$(GREEN)Building and starting all services...$(NC)"
	docker compose up -d --build
	@echo "$(GREEN)All services are running:$(NC)"
	@echo "  - aicore-api: http://localhost:8000"
	@echo "  - qdrant:     http://localhost:6333"
	@echo "  - postgres:   localhost:5432 (user/db: aicore)"
	@echo "  - aicore-embedding:  grpc://localhost:50051"

down:
	@echo "$(YELLOW)Stopping all services...$(NC)"
	docker compose down --remove-orphans
	@echo "$(GREEN)All services stopped.$(NC)"

aicore-down:
	@echo "$(YELLOW)Stopping aicore services...$(NC)"
	-docker compose stop aicore-api
	-docker compose rm -f aicore-api
	-docker rm -f aicore-api
	@echo "$(GREEN)aicore services stopped.$(NC)"

clean-aicore-api: aicore-down
	@echo "$(YELLOW)Removing aicore-api image...$(NC)"
	-docker rmi $$(docker compose images -q aicore-api 2>/dev/null) 2>/dev/null || true
	@echo "$(GREEN)aicore-api cleaned.$(NC)"

build-aicore-api:
	@echo "$(GREEN)Building and starting aicore-api...$(NC)"
	docker compose up -d --build aicore-api
	@echo "$(GREEN)aicore-api is running at http://localhost:8000$(NC)"

clean-build-aicore-api: clean-aicore-api build-aicore-api

embedding-down:
	@echo "$(YELLOW)Stopping aicore-embedding...$(NC)"
	-docker compose stop aicore-embedding
	-docker compose rm -f aicore-embedding
	-docker rm -f aicore-embedding
	@echo "$(GREEN)aicore-embedding stopped.$(NC)"

clean-embedding: embedding-down
	@echo "$(YELLOW)Removing aicore-embedding image...$(NC)"
	-docker rmi $$(docker compose images -q aicore-embedding 2>/dev/null) 2>/dev/null || true
	@echo "$(GREEN)aicore-embedding cleaned.$(NC)"

build-embedding:
	@echo "$(GREEN)Building and starting aicore-embedding...$(NC)"
	docker compose up -d --build aicore-embedding
	@echo "$(GREEN)aicore-embedding is running at grpc://localhost:50051$(NC)"

clean-build-embedding: clean-embedding build-embedding

clean-cache:
	@echo "$(YELLOW)Removing all build caches...$(NC)"
	@echo "$(YELLOW)Removing Docker build cache...$(NC)"
	docker builder prune -af

clean-novol:
	@echo "$(YELLOW)Stopping and removing all containers (keeping volumes)...$(NC)"
	docker compose down --remove-orphans --rmi all
	@echo "$(YELLOW)Removing Docker build cache...$(NC)"
	docker builder prune -af
	@echo "$(GREEN)Clean complete. Volumes preserved.$(NC)"
