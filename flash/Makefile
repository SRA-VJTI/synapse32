# Makefile to build UPduino v3.0 blinky.v  with icestorm toolchain

BUILD_DIR = build
PINDEF = up5k.pcf
DEVICE = up5k
TOP_MODULE = blink
TOP_MODULE_FILE = blink.v
#all v files in the current directory but not in the build directory and except blinky.v
OTHER_MODULES = $(filter-out $(TOP_MODULE_FILE), $(wildcard *.v))

#top module bin
$(TOP_MODULE).bin: $(BUILD_DIR)/$(TOP_MODULE).asc
	icepack $(BUILD_DIR)/$(TOP_MODULE).asc $(TOP_MODULE).bin

$(BUILD_DIR)/$(TOP_MODULE).asc: $(BUILD_DIR)/$(TOP_MODULE).json $(PINDEF)
	nextpnr-ice40 --$(DEVICE) --package sg48 --json $(BUILD_DIR)/$(TOP_MODULE).json --pcf $(PINDEF) --asc $(BUILD_DIR)/$(TOP_MODULE).asc

$(BUILD_DIR)/$(TOP_MODULE).json: $(TOP_MODULE_FILE) $(OTHER_MODULES)
	mkdir -p $(BUILD_DIR)
	yosys -p "synth_ice40 -top $(TOP_MODULE) -json $(BUILD_DIR)/$(TOP_MODULE).json" $(TOP_MODULE_FILE) $(OTHER_MODULES)

flash: $(TOP_MODULE).bin
	iceprog $(TOP_MODULE).bin

.PHONY: clean sim
clean:
	rm -rf $(BUILD_DIR) *.bin
