# Installing SearchOS

**English** | [简体中文](zh/installation.md)

For macOS and Linux, the recommended path is the one-command installer in the
repository root. It creates an isolated `.venv`, installs SearchOS and the
bundled Access Skill dependencies, downloads Playwright Chromium, and installs
the locked Web frontend dependencies with `npm ci`.

## Requirements

- Python 3.11 or later
- Node.js 20.9 or later when using the Web frontend
- npm

The installer prefers `python3.13`, `python3.12`, and then `python3.11`, so it
does not accidentally select the older `python3` bundled with macOS.

## One-command installation

```bash
./install.sh
source .venv/bin/activate
```

After installation, start either interface directly:

```bash
searchos
./web/start.sh
```

On the first SearchOS launch, the setup wizard asks you to select a model
provider and saves the required credentials to `.env`.

## Installation modes

```bash
./install.sh --core          # Core Python dependencies for the CLI/TUI and Web API only
./install.sh                 # Default: core + all Access Skills + Chromium + Web frontend
./install.sh --all           # Also install evaluation, optional search/browser, and observability dependencies
./install.sh --dev           # Add pytest and Ruff to the default installation
./install.sh --all --dev     # Complete development environment
./install.sh --no-web        # Skip Web frontend dependencies
./install.sh --no-browser    # Skip the Chromium download
```

Select a Python interpreter or virtual-environment path with an environment
variable or command-line option:

```bash
PYTHON=/path/to/python3.12 ./install.sh
./install.sh --python /path/to/python3.12 --venv .venv-searchos
```

## Manual installation

If you do not use the installer, install only the dependency groups you need:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .             # CLI/TUI and Web API
python -m pip install -e ".[access]"  # Bundled Access Skills
python -m pip install -e ".[dev]"     # Tests and linting
python -m pip install -e ".[all]"     # All optional runtime dependencies
```

After manually installing the Access Skill dependencies, install Chromium if
you intend to use browser-backed Skills:

```bash
python -m playwright install chromium
```

Install the Web frontend from its lockfile:

```bash
npm ci --prefix web/frontend
```

## Verify the installation

The one-command installer automatically runs these checks:

```bash
python -m pip check
searchos --help
```

If `./web/start.sh` reports an unsupported Python version or cannot find
SearchOS, run `./install.sh` first. The startup script prefers the repository's
own `.venv`.

## The `searchos` command points to another checkout

If `python -m searchos` works but the `searchos` traceback points to another
directory, your shell found a command installed in a different environment.
Check the executable first:

```bash
command -v searchos
head -n 5 "$(command -v searchos)"
```

Activate this repository's environment and refresh the shell command cache:

```bash
source .venv/bin/activate
hash -r
command -v searchos
```

The final command should point to `.venv/bin/searchos` inside this repository.
You can also run the executable directly without activating the environment:

```bash
./.venv/bin/searchos
```

Do not work around this problem by adding an API key requested by the foreign
traceback. That would continue running code from the wrong checkout.
