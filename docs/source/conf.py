from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

project = "DeepRootGen"
copyright = "2024, James Bristow"
author = "James Bristow"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.ifconfig",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
    "sphinxarg.ext",
    "myst_parser",
]

numpydoc_show_class_members = False

templates_path = ["_templates"]

source_suffix = {
    ".rst": "restructuredtext",
}

html_theme = "sphinx_rtd_theme"

# Enable only if docs/source/_static exists.
html_static_path = []

root_doc = "index"

today_fmt = "%d/%m/%y"