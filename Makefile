.PHONY: clean codegen build test deploy

clean:
	bash scripts/clean.sh

codegen:
	bash scripts/codegen.sh

build:
	bash scripts/build.sh

test:
	python -m pytest -q

deploy:
	bash scripts/deploy.sh
