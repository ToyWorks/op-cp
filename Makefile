# StackChan Dance — UIFlow2/MicroPython workflow for two boards.
#
# Same loop as OP-CP one directory up: `make check` proves a change on real
# hardware, `make shots` renders the face on the host. The toolchain venv is
# shared with it — both are plain mpremote + mpy-cross. Run `make venv` there
# first if ../.venv does not exist yet.
#
# BOARD is the only knob. The shared program is app.py + lib/; the board's own
# half is boards/$(BOARD)/, which lands on the device under the SAME names, so
# nothing on either machine ever tests which machine it is:
#
#   make check              # the CoreS3 on its StackChan base (the default)
#   make check BOARD=cube   # the xiaozhi-cube 1.54
#
# `make boards` lists what is attached and which name to use for it.

BOARD ?= cores3
BOARD_DIR := boards/$(BOARD)

VENV     := ../.venv
BIN      := $(VENV)/bin
PY       := $(BIN)/python3
MPREMOTE := $(BIN)/mpremote
MPYCROSS := $(BIN)/mpy-cross

# Three M5-flavoured boards share this desk (the Cardputer-ADV is the band),
# so the port match is on the product string, not just the manufacturer.
PORT ?= $(shell MPREMOTE=$(MPREMOTE) sh tools/find-port.sh $(BOARD))
DEV   = $(MPREMOTE) connect $(PORT)

APP     := app.py
SOURCES := $(APP) selftest.py
LIBS    := $(wildcard lib/*.py) $(wildcard $(BOARD_DIR)/*.py)
ART     := $(wildcard lib/*.png)   # hand sprites; tools/build_art.py renders

.DEFAULT_GOAL := help

## check: compile, upload, run the self-test on hardware, read the result back
.PHONY: check
check: compile push
	@echo "==> running selftest.py on $(BOARD) at $(PORT)"
	@$(DEV) run selftest.py

## compile: MicroPython syntax check — catches more than ast.parse, needs no board
.PHONY: compile
compile:
	@for f in $(SOURCES) $(LIBS); do \
		printf '==> mpy-cross %s\n' "$$f"; \
		$(MPYCROSS) "$$f" -o /dev/null || exit 1; \
	done

## compile-all: syntax check BOTH boards' halves, not just the selected one
.PHONY: compile-all
compile-all:
	@for f in $(SOURCES) lib/*.py boards/*/*.py; do \
		printf '==> mpy-cross %s\n' "$$f"; \
		$(MPYCROSS) "$$f" -o /dev/null || exit 1; \
	done

## push: copy app.py, lib/ and this board's half (flat — /flash has no dirs)
.PHONY: push
push:
	@echo "==> uploading $(BOARD) to $(PORT)"
	@$(DEV) fs cp $(APP) :app.py
	@for f in $(LIBS) $(ART); do $(DEV) fs cp "$$f" ":$$(basename $$f)"; done

## run: run app.py live — tracebacks come back here, Ctrl-C stops it
.PHONY: run
run:
	@echo "==> running $(APP) on $(BOARD) at $(PORT)  (Ctrl-C to stop)"
	@$(DEV) run $(APP)

## deploy: install as main.py so the dance starts on power-up, then reboot
.PHONY: deploy
deploy: compile bootopt
	@echo "==> installing $(APP) as main.py on $(BOARD) at $(PORT)"
	@$(DEV) fs cp $(APP) :main.py
	@for f in $(LIBS) $(ART); do $(DEV) fs cp "$$f" ":$$(basename $$f)"; done
	@$(DEV) reset
	@echo "==> deployed; board is rebooting into $(APP)"

## bootopt: NVS uiflow/boot_option = 0, so boot.py runs main.py on power-up
.PHONY: bootopt
bootopt:
	@$(DEV) run tools/bootopt.py

## undeploy: remove main.py, boot back to the UIFlow2 menu
.PHONY: undeploy
undeploy:
	@$(DEV) fs rm :main.py || true
	@$(DEV) reset

## shots: render the face states to sim/shots/$(BOARD)/ — then look at them
.PHONY: shots
shots:
	@$(PY) sim/shoot.py $(BOARD) 2

## art: re-render the hand sprites into lib/
.PHONY: art
art:
	@$(PY) tools/build_art.py

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

## boards: which boards are on USB, and the BOARD= name for each
.PHONY: boards
boards:
	@MPREMOTE=$(MPREMOTE) sh tools/find-port.sh --list

## repl / reset / port / ls / mem
.PHONY: repl reset port ls mem
repl:
	@$(DEV) repl
reset:
	@$(DEV) reset
port:
	@echo $(PORT)
ls:
	@$(DEV) fs ls :/flash
mem:
	@$(DEV) exec "import gc; gc.collect(); print('free', gc.mem_free(), 'alloc', gc.mem_alloc())"

## help
.PHONY: help
help:
	@grep -E '^## ' Makefile | sed 's/^## /  /'
	@echo ""
	@echo "  BOARD=cores3 (default) | cube"
