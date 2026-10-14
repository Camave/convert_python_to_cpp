# Python → C++ Migration Pipeline

An automated pipeline that analyses a Python script, categorises it (business domain, technical type, complexity), converts it to C++17 function by function with an LLM, and then **checks the conversion**: it compiles the C++ and reruns the original Python tests against it.

![Pipeline overview](Pipeline%20overview@1x.png)

A full description of the design is in [migrationPipeline.pdf](migrationPipeline.pdf).

---

## ✅ A generation has already been done

You don't need to run anything to see the results. The pipeline has already been run on [data/algorithms.py](data/algorithms.py), and everything it produced is committed in [sortie/](sortie/):

| File | Content |
|---|---|
| [sortie/metadonnees_algorithms.json](sortie/metadonnees_algorithms.json) | Answers to the case questions (business / technical categorisation, complexity, description), from both methods |
| [sortie/fiches_algorithms.json](sortie/fiches_algorithms.json) | Per-function analysis sheets |
| [sortie/conversion_algorithms.json](sortie/conversion_algorithms.json) | Conversion report: status, attempts and assumptions the LLM made for each function |
| [sortie/cpp/](sortie/cpp/) | Generated C++ (`algorithms.cpp/.hpp`), pybind11 bindings, support library `pysupport.hpp` |
| [sortie/validation_algorithms.json](sortie/validation_algorithms.json) | Validation result |
| [sortie/prompts/](sortie/prompts/) | Every prompt sent to the LLM, kept for traceability |
| [rapport/comparaison_regles_llm.md](rapport/comparaison_regles_llm.md) | Comparison of the rule-based and LLM categorisation methods on 12 scripts |

**Result of this run:** 6/6 functions converted, the C++ module compiles, **5/5 original tests pass** on the C++ version, and the console output of the C++ `main()` is **identical** to the Python one.

> ⚠️ Running `main.py` **deletes `sortie/`** before it starts. Commit or copy it first if you want to keep the reference generation.

---

## Pipeline steps

| Step | Module | What it does |
|---|---|---|
| 1. Extraction | `read_extract.py` | AST analysis + types (MonkeyType at runtime, Pyright statically) + conversion risk per function |
| 2a. Categorisation (rules) | `categorisation_regles.py` | Deterministic, keyword/import based |
| 2b. Categorisation (LLM) | `categorisation_llm.py` | LLM with a JSON schema it must follow, independent from 2a |
| 3. Conversion | `conversion.py` | C++17 function by function: prompt → LLM → clean-up → checks (signature, forbidden constructs, `g++`) → repair loop |
| 4. Validation | `validation.py` | Builds the C++ as a Python module (pybind11), reruns `test_<module>.py` on it, compares console output |

All prompts, models, type mappings and examples are in [config/](config/).

---

## Requirements

- **Python 3.11** (tested with 3.11.9)
- **g++ with C++17 support** on the `PATH` (tested with MinGW-w64 / MSYS2 g++ 15.2 on Windows; standard g++ on Linux/macOS)
- **An Ollama server** with these models pulled:
  - `qwen3.5:9b` (categorisation, set in `config/prompts_categorisation.json`)
  - `qwen3.6:35b-a3b` (conversion, set in `config/prompts_conversion.json`)

> ⚠️ **Ollama host:** the server address is hard-coded in [categorisation_llm.py](categorisation_llm.py) (`client = Client(host="http://100.114.26.31:11434")`). That address is a private server, so you cannot reach it. Change it to your own server, e.g. `http://localhost:11434`.

Steps 1, 2a and 4 do not need the LLM. Steps 2b and 3 do.

---

## Installation

```bash
git clone https://github.com/Camave/convert_python_to_cpp.git
cd convert_python_to_cpp

python -m venv env
# Windows
env\Scripts\activate
# Linux / macOS
source env/bin/activate

pip install -r requirements.txt
```

If you run Ollama locally:

```bash
ollama pull qwen3.5:9b
ollama pull qwen3.6:35b-a3b
```

---

## Running the pipeline

Full pipeline on the default script (`data/algorithms.py`):

```bash
python main.py
```

On another script:

```bash
python main.py path/to/your_script.py
```

For validation to rerun your tests, put a `test_<module>.py` file next to the script (e.g. `data/test_algorithms.py` next to `data/algorithms.py`).

Each step can also be run on its own:

```bash
python read_extract.py                            # step 1 on data/algorithms.py
python categorisation_llm.py data/algorithms.py   # step 2b
python validation.py data/algorithms.py           # step 4 only, reuses sortie/conversion_algorithms.json
```

---

## Testing

### Check the existing generation without the LLM

`validation.py` reuses the C++ already in `sortie/cpp/`, so you can recompile and test it without Ollama:

```bash
python validation.py data/algorithms.py
```

### Run the generated C++ as a standalone program

```bash
g++ -std=c++17 -O2 -Isortie/cpp sortie/cpp/algorithms.cpp lancer.cpp -o algorithms
./algorithms
```

Compare with the Python version:

```bash
python data/algorithms.py
```

### Unit tests of the Python sources

```bash
pytest data/test_algorithms.py
pytest data/analyse_code/test_analyse_code.py
pytest data/outils_pipeline/test_outils_pipeline.py
```

---

## Project structure

```
.
├── main.py                    # Runs the full pipeline
├── read_extract.py            # 1  - extraction
├── categorisation_regles.py   # 2a - rule-based categorisation
├── categorisation_llm.py      # 2b - LLM categorisation (Ollama client is configured here)
├── conversion.py              # 3  - Python -> C++ conversion
├── validation.py              # 4  - compile + rerun tests
├── lancer.cpp                 # Small C++ entry point to run the generated main()
├── config/                    # Prompts, models, type mappings, examples, pysupport.hpp
├── data/                      # Sample scripts to convert, with their tests
├── sortie/                    # Output of the reference run (see above)
└── rapport/                   # Rules vs LLM comparison
```
