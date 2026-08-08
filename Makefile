# StackChan Dance — UIFlow2/MicroPython workflow for the CoreS3 + StackChan base.
#
# Same loop as ../cardputer-adv-uiflow2: `make check` proves a change on real
# hardware, `make shots` renders the face on the host. The toolchain venv is
# shared with the Cardputer project — both are plain mpremote + mpy-cross.

VENV     := ../cardputer-adv-uiflow2/.venv
BIN      := $(VENV)/bin
PY       := $(BIN)/python3
MPREMOTE := $(BIN)/mpremote
MPYCROSS := $(BIN)/mpy-cross

# Two M5Stack boards share the desk (the Cardputer is the band), so the port
# match is on the CoreS3 product string, not just the manufacturer.
PORT ?= $(shell MPREMOTE=$(MPREMOTE) sh tools/find-port.sh)
DEV   = $(MPREMOTE) connect $(PORT)

APP     := app.py
SOURCES := $(APP) selftest.py
LIBS    := $(wildcard lib/*.py)
ART     := $(wildcard lib/*.png)   # hand sprites; tools/build_art.py renders

.DEFAULT_GOAL := help

## check: compile, upload, run the self-test on hardware, read the result back
.PHONY: check
check: compile push
	@echo "==> running selftest.py on $(PORT)"
	@$(DEV) run selftest.py

## compile: MicroPython syntax check — catches more than ast.parse, needs no board
.PHONY: compile
compile:
	@for f in $(SOURCES) $(LIBS); do \
		printf '==> mpy-cross %s\n' "$$f"; \
		$(MPYCROSS) "$$f" -o /dev/null || exit 1; \
	done

## push: copy app.py and lib/ to the device (flat — /flash has no lib dir)
.PHONY: push
push:
	@echo "==> uploading to $(PORT)"
	@$(DEV) fs cp $(APP) :app.py
	@for f in $(LIBS) $(ART); do $(DEV) fs cp "$$f" ":$$(basename $$f)"; done

## run: run app.py live — tracebacks come back here, Ctrl-C stops it
.PHONY: run
run:
	@echo "==> running $(APP) on $(PORT)  (Ctrl-C to stop)"
	@$(DEV) run $(APP)

## deploy: install as main.py so the dance starts on power-up, then reboot
.PHONY: deploy
deploy: compile
	@echo "==> installing $(APP) as main.py on $(PORT)"
	@$(DEV) fs cp $(APP) :main.py
	@for f in $(LIBS) $(ART); do $(DEV) fs cp "$$f" ":$$(basename $$f)"; done
	@$(DEV) reset
	@echo "==> deployed; board is rebooting into $(APP)"

## undeploy: remove main.py, boot back to the UIFlow2 menu
.PHONY: undeploy
undeploy:
	@$(DEV) fs rm :main.py || true
	@$(DEV) reset

## shots: render the face states to sim/shots/ on the host, then look at them
.PHONY: shots
shots:
	@$(PY) sim/shoot.py 2

## metrics: re-dump font metrics from the board (after a firmware update)
.PHONY: metrics
metrics:
	@$(DEV) run sim/dump_metrics.py > sim/metrics.json
	@echo "==> sim/metrics.json refreshed ($$(wc -c < sim/metrics.json) bytes)"

## probe: dump the M5 API surface this board actually has
.PHONY: probe
probe:
	@$(DEV) run tools/probe.py

## api: list attributes of one object, e.g. `make api OBJ=M5.Mic`
.PHONY: api
api:
	@test -n "$(OBJ)" || { echo "usage: make api OBJ=M5.Mic"; exit 1; }
	@$(DEV) exec "import M5; M5.begin(); print(sorted(x for x in dir($(OBJ)) if not x.startswith('_')))"

## repl / reset / port / ls / mem
.PHONY: repl reset port ls mem
repl:
	@$(DEV) repl
reset:
	@$(DEV) reset
port:
	@echo $(PORT)
	@$(MPREMOTE) devs | grep -i m5stack || true
ls:
	@$(DEV) fs ls :/flash
mem:
	@$(DEV) exec "import gc; gc.collect(); print('free', gc.mem_free(), 'alloc', gc.mem_alloc())"

## help
.PHONY: help
help:
	@grep -E '^## ' Makefile | sed 's/^## /  /'
