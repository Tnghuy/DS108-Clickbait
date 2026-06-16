# Contributing to Vietnamese Clickbait Dataset

First of all, thank you for your interest in contributing! This is an open-science project aimed at improving Vietnamese NLP dataset quality and reproducibility.

## Code of Conduct

We expect all contributors to maintain a professional, respectful, and inclusive environment.

## How to Contribute

### 1. Reporting Bugs
- Open an Issue describing the bug.
- Include environment details (Python version, OS, PyTorch version, Ollama availability).
- Provide a minimal reproducible example or step-by-step description to trigger the bug.

### 2. Suggesting Enhancements
- If you have ideas for improving the scraping heuristics, deduplication efficiency, or prompt engineering, open an Issue for discussion.
- If you plan to add new news sources, please describe them and verify their RSS/Sitemap compatibility.

### 3. Pull Requests (PRs)
- Fork the repository and create your branch from `main`.
- Install dependencies using the provided `requirements.txt` or Poetry:
  ```bash
  pip install -r requirements.txt
  ```
- Make your changes in a modular, clean, OOP manner.
- Ensure all unit tests pass:
  ```bash
  pytest
  ```
- If you introduce new logic (e.g. a new validation gate), please add corresponding tests under `tests/`.
- Ensure all text and code files are formatted cleanly and comments are written in English (or Vietnamese for reasoning samples).

### 4. Contributing New Annotations
- If you are manually reviewing borderline cases or disagreements using the CLI Reviewer (`python src/review/cli_reviewer.py`), please commit your `decisions_<username>.jsonl` to help enrich the gold-standard corpus.

## License

By contributing to this repository, you agree that your contributions will be licensed under the project's **MIT License** (for code) and **CC-BY-4.0** (for data).
