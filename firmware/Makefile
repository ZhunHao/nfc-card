# Host behavior tests and ATtiny1616 prototype builds.
CC      ?= clang
PYTHON  ?= python3
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O1 -g
# No default: name the card, so a plain `make` cannot build the wrong animation.
ifeq ($(strip $(BOARD)),)
$(error Set BOARD to orbit or terminal, e.g. make BOARD=orbit release)
endif
BUILD   ?= build/$(BOARD)
BOARD_DIR := boards/$(BOARD)
CPPFLAGS += -I$(BOARD_DIR) -Isrc
HOST_TESTS := $(BUILD)/test_charlieplex $(BUILD)/test_animation $(BUILD)/test_power $(BUILD)/test_scan $(BUILD)/test_hal $(BUILD)/test_app

.PHONY: test fixture test-sanitize clean

test: fixture $(HOST_TESTS)
	@$(BUILD)/test_charlieplex
	@$(BUILD)/test_animation
	@$(BUILD)/test_power
	@$(BUILD)/test_scan
	@$(BUILD)/test_hal
	@$(BUILD)/test_app

fixture:
	$(PYTHON) tests/check_board_fixture.py

$(BUILD)/test_%: tests/test_%.c src/%.c $(wildcard src/*.h) $(wildcard $(BOARD_DIR)/*.h) tests/fixtures/card_led_pairs.h
	@mkdir -p $(BUILD)
	$(CC) $(CPPFLAGS) -Isrc $(CFLAGS) $(LDFLAGS) -o $@ $< src/$*.c

$(BUILD)/test_animation: $(BOARD_DIR)/test_animation.c $(BOARD_DIR)/animation.c $(wildcard src/*.h) $(wildcard $(BOARD_DIR)/*.h)
	@mkdir -p $(BUILD)
	$(CC) $(CPPFLAGS) -Isrc $(CFLAGS) $(LDFLAGS) -o $@ $(filter %.c,$^)

test-sanitize:
	$(MAKE) test BUILD=build/sanitize CFLAGS='-std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined'

clean:
	rm -rf $(BUILD)

# Set AVR_PREFIX=/path/to/avr- for an explicitly selected toolchain.
AVR_PREFIX ?= avr-
AVR_CC ?= $(AVR_PREFIX)gcc
AVR_OBJCOPY ?= $(AVR_PREFIX)objcopy
AVR_OBJDUMP ?= $(AVR_PREFIX)objdump
AVR_SIZE ?= $(AVR_PREFIX)size
AVR_NM ?= $(AVR_PREFIX)nm
export AVR_CC AVR_OBJCOPY AVR_OBJDUMP AVR_SIZE AVR_NM

AVR_FLAGS ?= -std=c11 -O2 -g -Wall -Wextra -Werror -mmcu=attiny1616 -DF_CPU=1000000UL -ffunction-sections -fdata-sections -fstack-usage
export AVR_FLAGS
COMMON := src/charlieplex.c $(BOARD_DIR)/animation.c src/power.c src/scan.c src/hal_avr.c src/app.c
HOST_SUPPORT := tests/support/hal_test_backend.c

$(BUILD)/test_hal: tests/test_hal.c src/hal_avr.c src/charlieplex.c $(HOST_SUPPORT) $(wildcard src/*.h)
	@mkdir -p $(BUILD)
	$(CC) $(CPPFLAGS) -Isrc -Itests/support -DHAL_HOST_TEST $(CFLAGS) $(LDFLAGS) -o $@ $(filter %.c,$^)

$(BUILD)/test_app: tests/test_app.c $(COMMON) $(HOST_SUPPORT) $(wildcard src/*.h) $(wildcard $(BOARD_DIR)/*.h)
	@mkdir -p $(BUILD)
	$(CC) $(CPPFLAGS) -Isrc -Itests/support -DHAL_HOST_TEST $(CFLAGS) $(LDFLAGS) -o $@ $(filter %.c,$^)

.PHONY: avr avr-images verify verify-avr toolchain-check release
# Check tools before using artifacts, even when every image is up to date.
toolchain-check:
	$(PYTHON) tools/check_build.py --toolchain-only

avr: toolchain-check
	$(MAKE) --always-make avr-images

avr-images: $(BUILD)/animation.hex $(BUILD)/diagnostic.hex
	$(AVR_SIZE) $(BUILD)/animation.elf $(BUILD)/diagnostic.elf > $(BUILD)/size.txt
	@cat $(BUILD)/size.txt
	$(PYTHON) tools/check_build.py --build "$(BUILD)"
	$(PYTHON) tests/check_avr_timing.py $(BUILD)/animation.elf --objdump $(AVR_OBJDUMP) --nm $(AVR_NM)
	$(PYTHON) tests/check_avr_timing.py $(BUILD)/diagnostic.elf --objdump $(AVR_OBJDUMP) --nm $(AVR_NM)

$(BUILD)/animation.elf: $(COMMON) src/scan_isr.S src/main.c $(wildcard src/*.h) $(wildcard $(BOARD_DIR)/*.h) Makefile
	@mkdir -p $(BUILD)
	$(AVR_CC) $(CPPFLAGS) $(AVR_FLAGS) -Wl,--gc-sections,-Map,$(@:.elf=.map) -o $@ $(filter %.c %.S,$^)
	$(AVR_OBJDUMP) -d -S $@ > $(@:.elf=.lst)

$(BUILD)/diagnostic.elf: $(COMMON) src/scan_isr.S src/diagnostic.c $(wildcard src/*.h) $(wildcard $(BOARD_DIR)/*.h) Makefile
	@mkdir -p $(BUILD)
	$(AVR_CC) $(CPPFLAGS) $(AVR_FLAGS) -Wl,--gc-sections,-Map,$(@:.elf=.map) -o $@ $(filter %.c %.S,$^)
	$(AVR_OBJDUMP) -d -S $@ > $(@:.elf=.lst)

$(BUILD)/%.hex: $(BUILD)/%.elf
	$(AVR_OBJCOPY) -O ihex -R .eeprom $< $@

verify-avr: avr
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s tests -p test_release.py -v

# Run both portions even if the host suite fails; root gate aggregates hardware too.
verify:
	@status=0; \
	if $(MAKE) test; then echo 'PASS firmware:host'; else echo 'FAIL firmware:host'; status=1; fi; \
	if $(MAKE) verify-avr; then echo 'PASS firmware:avr'; else echo 'FAIL firmware:avr'; status=1; fi; \
	exit $$status

release: verify
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) tools/release.py --build "$(BUILD)"
