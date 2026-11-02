IMAGE ?= webapp-eval-runner:dev
JOBS ?= 2
PY ?= python3
export WEBEVAL_IMAGE := $(IMAGE)

.PHONY: test unit image check-verifiers selfcheck mutants agents judge report

# Clean clone -> green: harness unit tests, then every verifier must accept the
# reference and alternative fixes and reject the start state and the known-bad
# patches. Writes to .cache/ so it never overwrites the published results/.
test: unit image check-verifiers

unit:
	$(PY) -m unittest discover -s tests -t .

image:
	docker build -f docker/Dockerfile --build-arg KEZEK_SHA=$$(cat base/kezek.sha) -t $(IMAGE) .

check-verifiers:
	$(PY) -m harness.cli selfcheck -j $(JOBS) --out .cache/selfcheck

# The runs behind the numbers in README.md.
selfcheck: image
	$(PY) -m harness.cli selfcheck -j $(JOBS) --out results/selfcheck

mutants: image
	$(PY) -m harness.cli mutants -j $(JOBS)

agents: image
	$(PY) -m harness.cli agent --attempts 3 -j $(JOBS)

judge:
	$(PY) -m harness.cli judge --model sonnet

report:
	$(PY) -m harness.report
