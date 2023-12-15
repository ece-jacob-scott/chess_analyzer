PROJECT_NAME=chess_analyzer
SOURCE_FILES=chess_analyzer/*.py

# .PHONY: build
# build: $(SOURCE_FILES)
# 	@npm run build-tailwind
# 	@echo "built!"

.PHONY: create_database
create_database:
	@echo "Creating database..."
	flask --app chess_analyzer create_database

.PHONY: run
run: create_database
	flask --app chess_analyzer run

.PHONY: dev
dev: create_database
	flask --app chess_analyzer run --debug

.PHONY: localtunnel
localtunnel:
	@echo "make sure you are running the server locally in another terminal"
	@echo "Your public IP address is:"
	curl ipv4.icanhazip.com
	lt --port ${FLASK_RUN_PORT}
