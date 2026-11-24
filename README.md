
# Checkpoint Simulator

A local practice tool that replicates the Zone01 piscine checkpoint: timed, individual, sequential Go questions that get harder level by level, graded by hidden tests. Built with FastAPI and the Go toolchain, it serves a browser interface where you read a question, write your solution, run it in a terminal pane, and submit it for grading.

It exists for one purpose: to practice under checkpoint conditions (one question at a time, a countdown, hidden edge cases) before the real thing.

## Features

- 38 questions across 10 difficulty tiers (5% up to 100%), taken from the piscine subjects
- Each session picks one random question per tier, easiest first; the header shows `LEVEL n/10` for the tier (level 1 = 5%, level 2 = 10%, and so on)
- Sequential unlocking: you cannot see the next question until you pass the current one
- Server-side countdown timer, configurable minutes and question count (default 10 questions)
- Two separate actions: **Run** (your own `main.go` and arguments, output shown in a terminal pane) and **Submit** (your solution file graded against hidden tests)
- Hidden tests: a failed submit shows only the test number, with an optional "show failing test details" mode for practice
- Import restrictions enforced per question (for example, fprime may only import `os` and `z01`)
- A ready-written `main.go` for every function question, with example calls taken from the subject
- A built-in stand-in for the `github.com/01-edu/z01` package, so programs that use `z01.PrintRune` compile without installing it
- Questions stored as data in a JSON file, reloaded at the start of every session

## Tech Stack

- **Backend:** FastAPI served by Uvicorn
- **Validation:** Pydantic
- **Grading:** the Go toolchain (`go build`), driven from Python with `subprocess`
- **Frontend:** a single HTML page with vanilla JavaScript, no build step
- **Question bank:** JSON
- **Environment:** Python virtual environment (`venv`)

## Project Structure

```
checkpoint/
├── app.py           # API, session logic, Go runner
├── page.html        # the interface
├── questions.json   # the question bank
└── README.md
```

## Question Bank Format

There is no database. Every question is an entry in `questions.json`, which keeps question content separate from the code that grades it.

| Field | Purpose |
|---|---|
| `id`, `title` | Identifier and display name |
| `level` | The tier percentage (5, 10, 20, 35, 50, 65, 75, 85, 95, 100) |
| `kind` | `func` (you write a function) or `program` (you write a full `main`) |
| `allowed_imports` | Permitted imports: a list, an empty list for none, or `null` for no restriction |
| `statement` | The instructions shown in the left panel |
| `starter` | The code the editor starts with |
| `harness` | For `func` questions: a hidden `main` that turns arguments into inputs, calls your function and prints the result |
| `tests` | A list of test cases (see below) |
| `main_code`, `run` | Optional: a hand-written `main.go` and its expected output, for questions the generator cannot cover (slice arguments) |

A test is the command-line arguments plus the exact expected output:

```json
{ "args": ["Hello World"], "out": "Spwwz+bz}wo" }
```

### Tiers in the bank

| Level | Tier | Questions |
|---|---|---|
| 1 | 5% | 2 |
| 2 | 10% | 4 |
| 3 | 20% | 5 |
| 4 | 35% | 6 |
| 5 | 50% | 5 |
| 6 | 65% | 4 |
| 7 | 75% | 4 |
| 8 | 85% | 4 |
| 9 | 95% | 2 |
| 10 | 100% | 2 |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves the interface |
| GET | `/api/state` | Current session: time left, question number, current question details |
| POST | `/api/start` | Start a session (`minutes`, `count`, `details`) |
| POST | `/api/run` | Compile and run your files with the given arguments; returns terminal output |
| POST | `/api/submit` | Grade your solution against the hidden tests; unlocks the next question on a pass |

## How Grading Works

1. **Import check.** If the question restricts imports, a forbidden import fails immediately.
2. **Build.** The solution is written to a temporary Go project and compiled once. For `func` questions the hidden harness is added as `main.go`; for `program` questions your file is the `main`.
3. **Run.** Each test starts the compiled program with that test's arguments and a 5-second timeout.
4. **Compare.** The output must equal the expected output. Trailing newlines are ignored on both sides.
5. **Stop at the first failure.** A compile error, panic or timeout also fails, and those details are always shown.

## Known Limitations / Next Steps

- **The tests are a reconstruction, not the official ones.** They come from the examples in the subjects plus edge cases I added. Passing here does not guarantee passing the real checkpoint.
- **Not every piscine question is in the bank yet.** Several are missing (for example cleanstr, expandstr, iscapitalized, printmemory, printrevcomb, chunk, concatalternate, concatslice, canjump, reversestrcap, saveandmiss, addprimesum, onlya, onlyb, onlyf). Questions whose arguments are slices need a custom harness.
- **Newline handling is lenient.** Trailing newlines are ignored, so a missing final `\n` is not caught.
- **Slice arguments are passed as comma-separated text** in the hidden harness, so values containing commas cannot be tested.
- **One session at a time, kept in memory.** There are no accounts, and restarting the server ends the session.
- **Your code runs directly on your machine** with no sandbox, so only run code you wrote yourself.
- **No automated test suite yet.** The questions have not been verified end to end against reference solutions.
- **Question selection is random within a tier**, which is an assumption about how the real checkpoint chooses.

## Setup Instructions (Local Development)

1. Install Go and check that it is on your PATH:
   ```
   go version
   ```
2. Put `app.py`, `page.html` and `questions.json` in one folder, then create and activate a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install the dependencies:
   ```
   pip install fastapi uvicorn
   ```
4. Start the server:
   ```
   uvicorn app:app --reload
   ```
5. Open `http://127.0.0.1:8000`, choose the minutes and number of questions, and press Start.

Each new terminal needs `source venv/bin/activate` again before `uvicorn`.


## Adding a Question

1. Add an entry to `questions.json` with the fields above and a list of tests. Include edge cases: empty input, wrong argument count, boundary values.
2. For a function question, add a `harness` that calls your function with the arguments and prints the result.
3. Start a new session; the file is reloaded each time, so there is no need to restart the server.

## Running Tests

There is no automated test suite yet. To check a question, write a known-correct solution, start a session and submit it; every test should pass. To check a failure case, change the solution and confirm the right test number fails.