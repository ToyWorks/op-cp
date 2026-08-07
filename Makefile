# UIFlow2 / MicroPython workflow for the M5Stack Cardputer-ADV.
#
# There is no official UIFlow2 CLI — M5Burner is a GUI and the Web IDE is a
# browser. It doesn't matter: UIFlow2 firmware is MicroPython, so mpremote is
# the CLI, and `mpremote run` sends tracebacks back to stdout. That is the whole
# point of this Makefile: `make check` runs the code on real hardware and reads
# the result back, so a change can be verified without a human watching.

VENV     := .venv
BIN      := $(VENV)/bin
PY       := $(BIN)/python3
MPREMOTE := $(BIN)/mpremote
MPYCROSS := $(BIN)/mpy-cross
ESPTOOL  := $(BIN)/esptool

# The port is discovered, not hardcoded: any USB monitor or dock also shows up
# as /dev/cu.usbmodem*, so we match on the M5Stack manufacturer string.
# Override with `make check PORT=/dev/cu.usbmodemXXXX` if you have two boards.
PORT ?= $(shell MPREMOTE=$(MPREMOTE) sh tools/find-port.sh)
DEV   = $(MPREMOTE) connect $(PORT)

APP     := app.py
SOURCES := $(APP) selftest.py
LIBS    := $(wildcard lib/*.py)

.DEFAULT_GOAL := help

# ---------------------------------------------------------------- the loop

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

## push: copy app.py and lib/ to the device without making it the boot program
.PHONY: push
push:
	@echo "==> uploading to $(PORT)"
	@$(DEV) fs cp $(APP) :app.py
	@if [ -n "$(LIBS)" ]; then \
		$(DEV) fs mkdir :lib 2>/dev/null || true; \
		for f in $(LIBS); do $(DEV) fs cp "$$f" ":$$f"; done; \
	fi

## run: run app.py live on the device — tracebacks come back here, Ctrl-C stops it
.PHONY: run
run:
	@echo "==> running $(APP) on $(PORT)  (Ctrl-C to stop)"
	@$(DEV) run $(APP)

## deploy: install as main.py so the app starts on power-up, then reboot
.PHONY: deploy
deploy: compile
	@echo "==> installing $(APP) as main.py on $(PORT)"
	@$(DEV) fs cp $(APP) :main.py
	@if [ -n "$(LIBS)" ]; then \
		$(DEV) fs mkdir :lib 2>/dev/null || true; \
		for f in $(LIBS); do $(DEV) fs cp "$$f" ":$$f"; done; \
	fi
	@$(DEV) reset
	@echo "==> deployed; board is rebooting into $(APP)"

## undeploy: remove main.py so the board boots back to the UIFlow2 menu
.PHONY: undeploy
undeploy:
	@$(DEV) fs rm :main.py || true
	@$(DEV) reset

# ---------------------------------------------------------------- inspection

## probe: dump the M5 API surface this board actually has — check before calling
.PHONY: probe
probe:
	@$(DEV) run tools/probe.py

## api: list attributes of one object, e.g. `make api OBJ=M5.Lcd`
.PHONY: api
api:
	@test -n "$(OBJ)" || { echo "usage: make api OBJ=M5.Lcd"; exit 1; }
	@$(DEV) exec "import M5; M5.begin(); print(sorted(x for x in dir($(OBJ)) if not x.startswith('_')))"

## ls: list the device filesystem (/flash is the working dir and boot dir)
.PHONY: ls
ls:
	@$(DEV) fs ls :/flash

## mem: report free heap on the device
.PHONY: mem
mem:
	@$(DEV) exec "import gc; gc.collect(); print('free', gc.mem_free(), 'alloc', gc.mem_alloc())"

## repl: open an interactive REPL (Ctrl-] to exit)
.PHONY: repl
repl:
	@$(DEV) repl

## reset: reboot the board
.PHONY: reset
reset:
	@$(DEV) reset

## port: show which serial port was detected
.PHONY: port
port:
	@echo $(PORT)
	@$(MPREMOTE) devs | grep -i m5stack || true

# ---------------------------------------------------------------- setup

## venv: create the local toolchain (mpremote, mpy-cross, esptool)
.PHONY: venv
venv:
	python3 -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install mpremote mpy-cross esptool

## help: list targets
.PHONY: help
help:
	@echo "UIFlow2 / Cardputer-ADV"
	@echo
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  make /' | sed 's/: /\t/' | expand -t 18
	@echo
	@echo "  port: $(PORT)"
