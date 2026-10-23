# Configuration file for the Sphinx documentation builder.

# -- Project information -----------------------------------------------------
project = "Painel AVA"
copyright = "2026, IFRN - DEAD"
author = "IFRN - DEAD"
release = "1.1.064"

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
    "django_docs_theme",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
html_theme = "django_docs_theme"
html_theme_options = {
    "project_name": "Painel AVA",
    "tagline": "Middleware que conecta Sistemas de Gestão Acadêmica ao Moodle",
    "github_url": "https://github.com/suap-ava-suite/djangoapp-painel_ava",
    "doc_path": "docs/",
    "show_edit_on_github": True,
    "enable_dark_mode": True,
    "navigation_links": (
        "Início|index,"
        "Instalação e Testes|instalacao-e-testes,"
        "Nova API|nova-api,"
        "Evolução do Design|evolucao-do-design,"
        "Tipo de Commits|tipo-de-commits"
    ),
    "footer_custom_text": "Desenvolvido pela equipe IFRN - DEAD.",
}

html_static_path = ["_static"]
