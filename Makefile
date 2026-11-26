.PHONY: all install aws_cli aws_sam_cli pulumi uv shell check test test-backend test-integration test-web test-infra

all: install

install: aws_cli aws_sam_cli pulumi uv shell

aws_cli:
	curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
	unzip awscliv2.zip

	rm -rf ~/.aws-cli
	./aws/install -i ~/.aws-cli -b ~/.local/bin

	rm -f awscliv2.zip
	rm -rf aws

aws_sam_cli:
	curl -sL https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip -o aws-sam-cli-linux-x86_64.zip
	unzip aws-sam-cli-linux-x86_64.zip -d sam-installation

	rm -rf ~/.aws-sam-cli
	./sam-installation/install -i ~/.aws-sam-cli -b ~/.local/bin

	rm -f aws-sam-cli-linux-x86_64.zip
	rm -rf sam-installation

pulumi:
	curl -fsSL https://get.pulumi.com | sh

uv:
	curl -LsSf https://astral.sh/uv/install.sh | sh

shell:
	@echo "Instalação concluída. Adicione ao PATH da sua sessão:"
	@echo 'export PATH="$$HOME/.local/bin:$$HOME/.pulumi/bin:$$PATH"'

check:
	python3 -m py_compile pulumi/__main__.py aws-sam/functions/*/*.py

## ---- testes (mesmos passos do CI) ----------------------------------------
# Porta do DynamoDB Local usado pelos testes de integração.
DDB_PORT ?= 8001
PYTEST   := uv run --no-project --with-requirements requirements-test.txt pytest

test: test-backend test-integration test-web test-infra

test-backend:
	cd aws-sam && $(PYTEST) tests/unit

test-integration:
	docker run -d --rm --name classly-test-dynamodb -p 127.0.0.1:$(DDB_PORT):8000 amazon/dynamodb-local
	sleep 3
	cd aws-sam && DYNAMODB_ENDPOINT=http://127.0.0.1:$(DDB_PORT) $(PYTEST) tests/integration; \
		status=$$?; docker stop classly-test-dynamodb >/dev/null; exit $$status

test-web:
	cd web && npm ci && npm test && npm run build

test-infra:
	cd pulumi && uv run pytest tests
