.PHONY: build clean test verify runIde install help

GRADLE := ./gradlew

help:
	@echo "Targets:"
	@echo "  build    Build the plugin ZIP (-> build/distributions/)"
	@echo "  test     Run unit tests"
	@echo "  verify   Plugin Verifier against the IDEs in gradle.properties"
	@echo '           (add an installed one: make verify ide=$$HOME/Applications/GoLand.app)'
	@echo "  runIde   Launch a sandboxed PyCharm with the plugin loaded"
	@echo "  install  Print the ZIP path + manual install instructions"
	@echo "  clean    Clean build outputs"

build:
	$(GRADLE) buildPlugin

test:
	$(GRADLE) test

verify:
	$(GRADLE) verifyPlugin $(if $(ide),-PverifyLocalIde="$(ide)")

runIde:
	$(GRADLE) runIde

clean:
	$(GRADLE) clean

# Local install: this prints the ZIP location.
# Use "Settings > Plugins > gear icon > Install Plugin from Disk..." to install.
install: build
	@ZIP=$$(ls -t build/distributions/*.zip 2>/dev/null | head -n1); \
	  if [ -z "$$ZIP" ]; then echo "No ZIP found; did the build succeed?"; exit 1; fi; \
	  echo ""; \
	  echo "Built: $$ZIP"; \
	  echo ""; \
	  echo "To install:"; \
	  echo "  1. Open IDE → Settings → Plugins"; \
	  echo "  2. Click the gear icon → Install Plugin from Disk..."; \
	  echo "  3. Pick $$ZIP"; \
	  echo "  4. Restart the IDE"
