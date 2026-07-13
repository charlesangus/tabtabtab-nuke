# Build the distributable PDF user guide from the project readme.
#
#   make pdf        build docs/user-guide.pdf from readme.md
#   make clean      remove build intermediates (docs/.build/)
#   make distclean  also remove the committed docs/user-guide.pdf
#
# The readme is the single source of truth. `make pdf` derives a print-oriented
# Markdown copy (dropping the Contents, Demo GIFs, and Installation sections)
# and renders it with pandoc + xelatex, styled by docs/latex/training_doc.cls.
#
# Requires: pandoc, a xelatex-capable TeX Live (with texlive-latex-extra for
# adjustbox/koma-script), and python3.

PANDOC ?= pandoc
PYTHON ?= python3

DOCS_DIR      := docs
BUILD_DIR     := $(DOCS_DIR)/.build
README        := readme.md
USER_GUIDE_MD  := $(BUILD_DIR)/user-guide.md
USER_GUIDE_PDF := $(DOCS_DIR)/user-guide.pdf

PDF_DEFAULTS  := $(DOCS_DIR)/pandoc/pdf.yaml
IMAGE_FILTER  := $(DOCS_DIR)/pandoc/float-images.lua
BUILD_SCRIPT  := $(DOCS_DIR)/pandoc/build_user_guide_md.py
DOC_CLASS     := $(DOCS_DIR)/latex/training_doc.cls
DOC_LOGO      := $(DOCS_DIR)/latex/logo.pdf

# Let xelatex find training_doc.cls. The trailing empty entry keeps the default
# search path. Images are referenced relative to the repo root (where make runs),
# so pandoc resolves docs/images/... without any extra resource path.
export TEXINPUTS := $(CURDIR)/$(DOCS_DIR)/latex:

.PHONY: pdf clean distclean

pdf: $(USER_GUIDE_PDF)

$(USER_GUIDE_PDF): $(README) $(PDF_DEFAULTS) $(IMAGE_FILTER) $(BUILD_SCRIPT) $(DOC_CLASS) $(DOC_LOGO) | $(BUILD_DIR)
	$(PYTHON) $(BUILD_SCRIPT) $(README) $(USER_GUIDE_MD)
	$(PANDOC) --defaults $(PDF_DEFAULTS) \
		--lua-filter $(IMAGE_FILTER) \
		-o $@ $(USER_GUIDE_MD)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)

# The PDF is a tracked artifact shipped in the release zip, so removing it is
# kept out of `clean` (which would otherwise leave the repo dirty). Use this
# target when you deliberately want to drop the built PDF too.
distclean: clean
	rm -f $(USER_GUIDE_PDF)
