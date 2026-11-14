.PHONY: install compile clean link test

# Install dependencies
install:
	npm install

# Compile TypeScript
compile: install
	./node_modules/.bin/tsc -p .

# Clean build artifacts
clean:
	rm -rf out/

# Run tests
test: compile
	npm test

# Symlink into VS Code extensions for local development
# VS Code 1.118+ requires the dir name to follow `<publisher>.<name>-<version>`.
EXT_NAME := $(shell node -p "require('./package.json').publisher + '.' + require('./package.json').name + '-' + require('./package.json').version")
link: compile
	# Remove any stale entries: the extension's ids before the Verso brand, older versions
	rm -rf ~/.vscode/extensions/genealogy-dsllint ~/.vscode/extensions/*.genealogy-dsllint-*
	rm -rf ~/.vscode/extensions/verso-genealogy.verso-dsllint-*
	ln -sfn $(CURDIR) ~/.vscode/extensions/$(EXT_NAME)
	@echo "Linked as $(EXT_NAME). Restart VS Code to activate."

# Build VSIX package (requires vsce: npm install -g @vscode/vsce)
package: compile
	vsce package
