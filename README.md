# Smart Fitness Session Analyzer, Assignment II

**Python Programming Assignment II · Option A**

**Student name:** Abdirahman Ibrahim
**Student number:** 421971

## Contents

1. [Where Assignment I stopped, and why that was not enough](#1-where-assignment-i-stopped-and-why-that-was-not-enough)
2. [What the program does](#2-what-the-program-does)
3. [How to install and run](#3-how-to-install-and-run)
4. [The journey of one row](#4-the-journey-of-one-row)
5. [Package and module design](#5-package-and-module-design)
6. [Class design and the object oriented principles](#6-class-design-and-the-object-oriented-principles)
7. [Reading the files safely](#7-reading-the-files-safely)
8. [Handling errors: three custom exceptions and where they are caught](#8-handling-errors-three-custom-exceptions-and-where-they-are-caught)
9. [The two regular expressions](#9-the-two-regular-expressions)
10. [When is a row rejected?](#10-when-is-a-row-rejected)
11. [How is the verdict chosen?](#11-how-is-the-verdict-chosen)
12. [The three output files](#12-the-three-output-files)
13. [What the official data produced](#13-what-the-official-data-produced)
14. [Testing](#14-testing)
15. [What changed since Assignment I](#15-what-changed-since-assignment-i)
16. [Assumptions and known limitations](#16-assumptions-and-known-limitations)
17. [Where each requirement is met](#17-where-each-requirement-is-met)
18. [Summary](#18-summary)

## 1. Where Assignment I stopped, and why that was not enough

Assignment I opened with a picture: a good personal trainer standing next to you in the gym, who never asks whether a heart rate of 120 is high, only whether it is high **for you**. That program worked, but it lived in a bubble. Its data was handed to it by a generator inside the same folder, already tidy, already the right type, already about a person it knew.

Real measurements do not arrive that way. They arrive as a file somebody exported, with a stray word where a number should be, a participant who is not in the register, a row that lost a column on the way, and a sensor that was loose for five minutes. A trainer who throws up her hands at the first odd line is no use to anybody.

So Assignment II asks a harder question than Assignment I did. Not *can you judge a session*, but **can you keep judging sessions when the data fights back**. That is the thread running through everything below: the program reads what it can, writes down exactly what it refused and why, and never stops because of one bad line.

Terminology used throughout, in plain words:

| Word | What it means here |
|---|---|
| **row** | one line in a CSV file |
| **window** | one accepted measurement, taken at one point in a session |
| **session** | all the windows that share one session identifier |
| **baseline** | a participant's own normal value, their personal yardstick |
| **rejection** | a row the program refused, together with the reason |

## 2. What the program does

For every run, the program:

1. reads the **participant file** and builds one object per person, with their baselines;
2. reads **both session files**, the valid one and the intentionally invalid one;
3. **converts** each value to a real number instead of leaving it as text;
4. **validates** every row: identifiers, missing fields, row length, types, ranges, signal quality, duplicates, unknown participants;
5. **writes down** every refused row with its file, line number, field and reason, then carries on;
6. **groups** accepted windows into sessions and connects each session to its participant;
7. **analyses** each session: averages, minimum and maximum, comparison with the baselines, and a search for a cool down;
8. **classifies** the session as resting, moderate activity, high activity, recovering or insufficient data, with a reason in plain words;
9. **creates the output directory** if it is missing and writes three report files;
10. prints a short **completion summary**: rows accepted, rows rejected, files written.

The program uses only the Python standard library. No pandas, NumPy, scikit-learn, database, external API, graphical interface or machine learning model.

## 3. How to install and run

Nothing needs to be installed. `requirements.txt` only states that the standard library is used.

```bash
git clone https://github.com/abdirahmanibrahim15252-blip/fitness_analyzer_ii.git
cd fitness_analyzer_ii
python3 main.py
```

On Windows the command is often `python` instead of `python3`, for example `python main.py`.

Running `python3 main.py` with no arguments uses the official files. To name the files yourself, which is the form the assignment asks for:

```bash
python3 main.py --profiles data/participants.csv \
    --sessions data/fitness_sessions.csv data/fitness_sessions_invalid.csv \
    --output output
```

| Option | Meaning | Default |
|---|---|---|
| `--profiles` | the participant profile file | `data/participants.csv` |
| `--sessions` | one or more session files | both official session files |
| `--output` | where the reports are written | `output` |
| `--quiet` | print only the completion summary | off |

Run the automated tests:

```bash
python3 tests.py
```

The program never changes the official CSV files and never uses an absolute path. Paths you pass on the command line are read relative to where you are standing; the defaults are found relative to the repository itself, so the program also works when called from another directory.

### Repository structure

```
main.py                     the entry point, four lines of real code
fitness_analyzer/           the package
  __init__.py               the module map
  errors.py                 the exception types
  validation.py             identifier patterns, type conversion, range checks
  models.py                 Participant, Observation, Session
  loading.py                reads CSV files, rejects what it cannot trust
  analysis.py               standalone calculations
  rules.py                  the classification rule hierarchy
  analyzer.py               applies the rules, builds the result
  reporting.py              console text and the three output files
  cli.py                    command line and completion summary
data/                       the official CSV files, unchanged
tests.py                    61 automated tests
requirements.txt            states that only the standard library is used
output/                     created by the program, not stored in git
```

## 4. The journey of one row

One line of CSV, followed from the file to the verdict. This is the red thread; everything in sections 5 to 12 is a close up of one step here.

```
 fitness_sessions_invalid.csv
   line 11:  FIT-2026-102,P002,4,126,-0.50,55.0,1.30,0.91
        │
        ▼
 loading._inspect_row()        checks the row and collects EVERY problem
        │                        skin_response -0.5   below 0
        │                        temperature   55.0   above 42
        │                        activity      1.30   above 1
        ▼
 Rejection objects             one per problem, each carrying
        │                      file, line number, field and reason
        ▼
 LoadResult                    the row is counted against session FIT-2026-102
        │                      and the loader moves to line 12
        ▼
 rejected_records.txt          "row 11  field temperature  invalid value
        │                       55.0 is outside the possible range 25.0 to 42.0"
        ▼
 the session is still analysed, and reports 0 of 4 rows usable
                               → verdict: insufficient data
```

A row that fails is never silently dropped, and it never takes the run down with it. Both halves of that sentence matter: the first is honesty, the second is usefulness.

## 5. Package and module design

The application is a Python package, `fitness_analyzer`, with nine modules. The assignment warns that more modules do not automatically make a better design, so here is the test each one had to pass: **can I say what it does in one line, and could I change it without opening the others?**

| Module | One line | Depends on |
|---|---|---|
| `errors` | the exception types the package raises | nothing |
| `validation` | identifier patterns, type conversion, range checks | `errors` |
| `models` | the domain objects and their invariants | `errors`, `validation` |
| `loading` | reads CSV files and refuses what it cannot trust | `errors`, `validation`, `models` |
| `analysis` | calculations on plain lists of numbers | nothing |
| `rules` | one class per possible verdict | `analysis` |
| `analyzer` | applies the rules and builds the result | `analysis`, `rules`, `models` |
| `reporting` | console text and the three output files | `analysis`, `errors` |
| `cli` | command line, orchestration, completion summary | all of the above |

Read the table downwards and the dependencies only ever point upwards. `analysis` knows nothing about files; `models` knows nothing about CSV; `reporting` knows nothing about rules. That is why a change to the output format cannot break the classification, and why `analysis.py` can be tested with six plain numbers and no file at all.

## 6. Class design and the object oriented principles

Eleven classes, carried over from Assignment I and adapted. Each principle is explained in one sentence and then pointed at in the code.

| Class | Module | Responsibility |
|---|---|---|
| `Participant` | models | a person and their three baselines |
| `Observation` | models | one accepted measurement window |
| `Session` | models | one participant composed with many windows |
| `Rejection` | loading | one reason one row was refused |
| `LoadResult` | loading | everything one load produced |
| `SessionAnalyzer` | analyzer | applies the rules, builds the result |
| `ClassificationRule` | rules | the base class for a verdict |
| `InsufficientDataRule`, `RecoveryRule`, `ThresholdRule`, `HighActivityRule`, `ModerateActivityRule`, `RestingRule` | rules | the verdicts themselves |
| `FitnessAnalyzerError` and its four subclasses | errors | what went wrong, and whether the program can continue |

### Composition

*Composition means an object is built from other objects, the way a car has an engine.*

A `Session` **has** a `Participant` and **has many** `Observation` objects. A `LoadResult` **has** many sessions and many rejections. A `SessionAnalyzer` **has** an ordered list of rule objects.

### Encapsulation

*Encapsulation means an object protects its own data and only allows changes through its own methods.*

1. `Participant` keeps its baselines in protected attributes such as `_baseline_heart_rate`. They can only be replaced through a property setter that validates the value, so `participant.baseline_heart_rate = 300` raises an error and the old value survives untouched.
2. `participant_id`, `name` and `session_id` are read only properties.
3. `Session` keeps its windows in `_observations` and hands them out only as a tuple. The single way in is `add_observation()`, which also refuses a duplicate timestamp.

There is a deliberate overlap worth naming. The loader checks a row **and** the model checks itself. That is not an accident: **the loader explains, the model enforces.** The loader's job is to tell a human why a row was refused, so it collects every problem in the row. The model's job is to make a bad object impossible, including in code the loader never touches, such as a test. Remove the loader check and the reports become vague; remove the model check and a future caller can build nonsense.

### Inheritance and method overriding

*Inheritance lets a class reuse another class. Overriding lets the child replace a method with its own version.*

`ClassificationRule` defines `matches()` and `explain()`. Every verdict **overrides** both with its own logic and its own wording. `HighActivityRule` and `ModerateActivityRule` inherit from `ThresholdRule` and change only the limits and the label. `evaluate()` is written once in the base class and never overridden, so the analyzer can ask every rule the same question without knowing which rule it is talking to.

The exception hierarchy uses inheritance for a second, quieter purpose: `InvalidIdentifierError` **is an** `InvalidRecordError`, because a bad identifier is a kind of bad record. A caller that only wants to reject the row catches the parent and gets both.

### Class methods and static methods

| Method | Kind | Why it is justified |
|---|---|---|
| `Participant.from_row(row)` | class method | an alternative constructor for one converted profile row |
| `SessionAnalyzer.with_default_rules()` | class method | keeps the rule order in one documented place |

## 7. Reading the files safely

Every file is opened with `open(..., encoding="utf-8", newline="")` and read with Python's `csv` module, as the assignment requires. Paths are `pathlib.Path` objects throughout, so the program behaves the same on Windows and on Linux.

Three details are worth pointing out, because they are the difference between a reader that works and a reader that works on somebody else's machine:

- **The header is checked before any row is read.** If the columns are not exactly the expected ones, the program stops with a message naming what it expected and what it found. A file with shuffled columns is more dangerous than a missing file, because it fails quietly.
- **A byte order mark is stripped.** Spreadsheet software often writes an invisible marker at the start of a UTF-8 file, which would otherwise turn `session_id` into something that matches nothing.
- **Line numbers come from `reader.line_num`,** so a rejection points at the physical line in the file. Open the file, go to that line, and the problem is there.

## 8. Handling errors: three custom exceptions and where they are caught

The hierarchy answers one question: **can the program carry on?**

```
FitnessAnalyzerError
├── DataFileError          a whole file is unusable      → the run stops, exit status 1
├── ReportWriteError       the output cannot be written  → the run stops, exit status 1
└── InvalidRecordError     one row is unusable           → the row is recorded, the run continues
    └── InvalidIdentifierError   an identifier is malformed
```

`InvalidRecordError` and `InvalidIdentifierError` also inherit from `ValueError`, so they behave the way a caller expects. `InvalidRecordError` carries a **list** of problems rather than one string, which is why row 11 of the invalid file is explained in three lines instead of one.

Every `try` block in the program is targeted at the error it can actually do something about. There is no empty `except`, and `except Exception` is never used as the error handling strategy.

| Where | Caught | What the program does |
|---|---|---|
| `loading._open_csv` | `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `OSError` | turns it into a `DataFileError` that names the file |
| `loading._read_header` | `StopIteration`, `csv.Error` | reports an empty or unreadable file |
| `loading._load_one_session_file` | `csv.Error` | reports the line where the CSV itself broke |
| `loading._handle_row` | `InvalidRecordError` | records the rejection and moves to the next row |
| `loading._inspect_row` | `InvalidIdentifierError`, **`KeyError`** | a bad identifier, or a participant who is not in the register |
| `validation.to_int`, `to_float` | `TypeError`, `ValueError` | turns a failed conversion into a readable reason |
| `reporting.ensure_output_directory` | `PermissionError`, `OSError` | turns it into a `ReportWriteError` |
| `reporting._open_for_writing` | `PermissionError`, `OSError` | the same, naming the file |
| `cli.main` | `DataFileError`, `ReportWriteError` | prints the message and returns exit status 1 |

The `KeyError` is worth a sentence of its own. Looking up an unknown participant is a dictionary miss, which Python signals with `KeyError`. Caught at the point of the lookup, it becomes the sentence *"P999 is not listed in the participant file"*. Left uncaught, it would end the run with a traceback and the single character `'P999'`.

## 9. The two regular expressions

Regular expressions are used for identifiers and nothing else. A pattern can say whether text is shaped like a participant identifier; it cannot say whether 265 is a plausible heart rate. Numeric limits are therefore ordinary comparisons, exactly as the assignment instructs.

| Value | Required format | Pattern | Matched with |
|---|---|---|---|
| Participant ID | P followed by three digits | `^P\d{3}$` | `fullmatch` |
| Session ID | FIT-YYYY-NNN | `^FIT-(\d{4})-(\d{3})$` | `fullmatch` |

Both are anchored **and** matched with `fullmatch`, which is belt and braces on purpose: `re.match` alone would happily accept `P001xyz`.

The session pattern has brackets around the year and the number. The same compiled pattern that validates an identifier also takes it apart, so `session_year("FIT-2026-007")` returns `2026` and the format is described in exactly one place in the whole program. Change the format once, and both validation and parsing follow.

## 10. When is a row rejected?

A row is rejected if **any** of the following is true. Every problem in the row is recorded, not only the first one found.

| Check | Rule | Category in the report |
|---|---|---|
| Row length | exactly 8 fields | format problem |
| `session_id` | matches `^FIT-(\d{4})-(\d{3})$` | format problem |
| `participant_id` | matches `^P\d{3}$` | format problem |
| Participant exists | the identifier is in `participants.csv` | unknown participant |
| Empty field | every field has a value | missing value |
| `timestamp` | a whole number, 0 or greater | invalid value |
| `heart_rate` | 35 to 205 bpm | invalid value |
| `skin_response` | 0 to 20 units | invalid value |
| `temperature` | 25 to 42 degrees Celsius | invalid value |
| `activity_level` | 0 to 1 | invalid value |
| `signal_quality` | 0 to 1 | invalid value |
| Signal reliability | `signal_quality` of 0.60 or more | low signal quality |
| Duplicate | no two windows share a timestamp in one session | duplicate window |

**The documented signal quality rule.** `signal_quality` is the device's own confidence in its reading. Below **0.60** the device is telling you not to trust it, so the window is rejected and recorded under its own category, separate from malformed rows. The categories matter: a session rejected because the strap was loose is a different conversation from a session rejected because the export was broken, and the report keeps them apart.

**Why the ranges are what they are.** They come from the supplied data dictionary and from what is physically possible. A heart rate of 265 is not an athlete, it is a sensor fault. A skin temperature of 55 degrees is not a person. An activity level of 1.30 is outside a scale that is defined as 0 to 1.

## 11. How is the verdict chosen?

The rules are asked **in this order**, and the first one that matches wins.

| Priority | Verdict | Condition |
|---|---|---|
| 1 | insufficient data | fewer than 4 usable windows, **or** fewer than 50% of the session's rows usable |
| 2 | recovering | real effort earlier, and a clear fall by the end (below) |
| 3 | high activity | average activity 0.67 or more, **or** heart rate 45 bpm or more above baseline |
| 4 | moderate activity | average activity 0.30 or more, **or** heart rate 15 bpm or more above baseline |
| 5 | resting | everything else, on data the program trusts |

**Order is a design decision, not an accident.** Data quality is asked first, because a confident verdict built on broken data is worse than no verdict. Recovery is asked before intensity, because a session with a hard middle has a high average that would otherwise be read as effort rather than as a cool down. Session FIT-2026-004 is exactly that case: its average heart rate sits 45.2 bpm above baseline, which reaches the high activity limit, yet the session ends with the participant nearly back to resting. Asked in this order, the program says *recovering*. Asked in the other order, it would say *high activity* and be wrong.

### The improved recovery rule

This is the part of Assignment I that most needed fixing.

Assignment I compared the **first third** of a session with the **last third**. That works for a session that starts hard. It misreads a session that opens with a warm up, because the quiet opening drags the early average down and hides the fall at the end.

Session FIT-2026-004 proves it. Heart rates: 72, 138, 151, 132, 104, 82.

| Rule | What it measures | Result |
|---|---|---|
| Assignment I | first third 105, last third 93, a fall of 12 bpm | below the 15 bpm limit, **missed** |
| Assignment II | peak 151, ending at 93, only 30% of the rise left | **recovery detected** |

The new rule measures the fall **from the session's own peak**, and requires all four of these:

1. the peak is at least 25 bpm above baseline, so there was real effort to recover from;
2. the peak happens before the final phase, so the effort is behind the participant;
3. by the end, no more than 40% of the peak rise in heart rate is left;
4. by the end, movement has fallen to no more than 50% of its peak.

Conditions 1 and 2 stop a quiet session being called a recovery on the strength of random noise. Conditions 3 and 4 ask for agreement between two independent signals: a heart rate that falls while the person is still moving hard is a different story, and not this one.

**Why the floor moved from six windows to four.** In Assignment I the generator never produced fewer than six windows, so six was a safe floor. The official CSV contains a five row session, which a floor of six would have refused for the wrong reason. The floor is now four usable windows **and** at least half of the session's rows, so a short session is judged on whether most of it survived, not on a number chosen for a different dataset.

## 12. The three output files

The program creates the output directory when it does not exist, and writes:

```
output/
├── analysis_summary.csv     one row per session, 18 columns
├── analysis_report.txt      the readable explanation of every result
└── rejected_records.txt     every refused row, with the reason
```

**Running the program again is safe.** Files are replaced, never appended to, sessions are written in identifier order, and nothing in any output file contains a clock time or a run number. Two runs over the same input therefore produce byte for byte identical files, which is verified by a test. There is no manual cleanup to remember.

`analysis_summary.csv`, first rows, trimmed to fit:

```
session_id,participant_id,participant_name,classification,total_rows,usable_rows,...
FIT-2026-001,P001,Amina Noor,resting,6,6,0,100.0,68.8,0.8,...
FIT-2026-004,P001,Amina Noor,recovering,6,6,0,100.0,113.2,45.2,...
FIT-2026-005,P002,Jonas Berg,insufficient data,5,0,5,0.0,,,...
```

`analysis_report.txt`, one session:

```
==============================================================================
 SESSION FIT-2026-004 · Amina Noor (P001)
==============================================================================
 Verdict   RECOVERING
 Why       Heart rate peaked at 151 bpm, which is 83 bpm above baseline, then
           fell to 93 bpm by the end. Only 30% of that rise is left, and
           movement fell from 0.92 to 0.30. The body was winding down after
           effort.

 Data quality: 6 of 6 rows usable (100.0%), source fitness_sessions.csv

 Measurement       Average      Min      Max   Compared with personal baseline
 -----------------------------------------------------------------------------
 Heart rate          113.2     72.0    151.0   45.2 bpm above baseline
 Skin response        2.58     1.35     3.90   1.38 units above baseline
 Temperature         33.28    32.60    33.90   0.88 C above baseline
 Activity             0.55     0.18     0.92   no personal baseline
 Signal quality       0.96     0.94     0.97   no personal baseline

 Recovery check: peak 151 bpm (83 above baseline), ending at 93 bpm, activity
                 0.92 to 0.30: recovery detected.
==============================================================================
```

`rejected_records.txt`, the invalid file:

```
fitness_sessions_invalid.csv
----------------------------
  row   3  field heart_rate       invalid value       'fast' is not a number
  row   4  field participant_id   format problem      '001' does not match the required format P followed by three digits
  row   5  field activity_level   missing value       has no value
  row   6  field signal_quality   invalid value       1.4 is outside the possible range 0.0 to 1.0
  row   7  field session_id       format problem      'FIT-26-102' does not match the required format FIT-YYYY-NNN
  row   8  field participant_id   unknown participant P999 is not listed in the participant file
  row   9  field timestamp        invalid value       'two' is not a whole number
  row  10  field heart_rate       invalid value       -15.0 is outside the possible range 35.0 to 205.0
  row  11  field activity_level   invalid value       1.3 is outside the possible range 0.0 to 1.0
  row  11  field skin_response    invalid value       -0.5 is outside the possible range 0.0 to 20.0
  row  11  field temperature      invalid value       55.0 is outside the possible range 25.0 to 42.0
  row  12  field row              format problem      has 7 fields, expected 8

Reasons by category
-------------------
  format problem        3
  invalid value         8
  low signal quality    5
  missing value         1
  unknown participant   1
```

Note row 11. One row, three independent faults, three lines. A reader does not have to run the program four times to discover them one at a time.

## 13. What the official data produced

```
 OVERVIEW
 ================================================================
 Session         Participant   Rows      Verdict
 ----------------------------------------------------------------
 FIT-2026-001    P001          6/6       resting
 FIT-2026-002    P002          6/6       moderate activity
 FIT-2026-003    P003          6/6       high activity
 FIT-2026-004    P001          6/6       recovering
 FIT-2026-005    P002          0/5       insufficient data
 FIT-2026-101    P001          1/5       insufficient data
 FIT-2026-102    P002          0/4       insufficient data

 COMPLETED
   participants loaded : 3
   sessions analysed   : 7
   rows accepted       : 25
   rows rejected       : 15
   files written       : output/analysis_summary.csv, output/analysis_report.txt, output/rejected_records.txt
   no usable rows for  : FIT-2026-103, FIT-26-102
```

Three things in that output are worth reading twice.

**All five verdicts appear.** The official data happens to exercise every branch of the classifier, which is the best evidence a rule set can have: it was not tuned to produce one answer.

**FIT-2026-005 is reported, not lost.** Every one of its five rows was rejected for low signal quality, so there is nothing to average. A careless program would quietly drop a session with no usable rows. This one still names it, still names the participant, and says *insufficient data* with the count to back it up. The sensor failed, not the athlete, and the report says so.

**Nothing disappears.** `FIT-2026-103` and `FIT-26-102` never produced a single usable row, so no analysis was possible. They are listed anyway, in the completion summary and at the end of the report, pointing the reader at `rejected_records.txt`. The last line of the summary exists so that no identifier can vanish between the input and the output.

## 14. Testing

```bash
python3 tests.py
```

**61 tests**, running in well under a second, using only `unittest`. They are grouped to match the four cases the assignment asks for.

| Group | What it proves | Examples |
|---|---|---|
| Valid data | the happy path really works | the official files load; all 7 sessions get the expected verdict; all five categories appear |
| Invalid data | every documented fault is caught | each of the 12 problems in the invalid file is found at the right line and field; each custom exception is raised |
| Missing files | a file problem stops the run cleanly | missing file, a directory where a file was expected, an empty file, wrong columns, an output path blocked by a file |
| Boundary values | the limits are exactly where they are documented | `signal_quality` 0.60 accepted and 0.59 rejected; heart rate 35 and 205 accepted, 34.9 and 205.1 rejected; activity 0.0 and 1.0 accepted, 1.01 rejected; 3 usable windows refused, 4 accepted |

Two tests deserve naming:

- `test_recovery_after_a_warm_up` does not only check that the new rule finds the cool down. It also asserts that the **old** first third rule would have missed it, so the improvement described in section 11 is proven by the test suite rather than merely claimed.
- `test_running_twice_produces_identical_files` runs the whole program twice into the same directory and compares the bytes. That is what makes the promise in section 12 something more than a good intention.

## 15. What changed since Assignment I

| Assignment I | Assignment II | Why |
|---|---|---|
| a generator module inside the project | three CSV files read from disk | the point of the assignment |
| flat files in one folder | a package with nine modules | the program got big enough that layers help |
| `Observation` carried a list of its own problems | `Session` holds only trustworthy windows; the loader owns rejection reporting | there was nowhere else to put problems in Assignment I; now there is, and the model gets simpler |
| no custom exceptions | four, in a hierarchy that says whether the run can continue | files fail in ways lists and dictionaries do not |
| no identifiers to check | two anchored regular expressions, used with `fullmatch` | files carry identifiers; generators do not |
| recovery judged by first third against last third | recovery judged by the fall from the session peak | the old rule missed a session that opens with a warm up, section 11 |
| at least 6 usable windows required | at least 4 usable windows and half the rows | the real data contains a five row session |
| printed to the console | writes three files and prints a completion summary | somebody has to be able to read it tomorrow |
| 25 tests | 61 tests | more ways to fail means more things to check |

## 16. Assumptions and known limitations

**Assumptions**

1. The columns in the official files are the ones in the supplied data dictionary, and a file with different columns is a mistake worth stopping for.
2. The ranges in section 10 describe what is physically possible for this device.
3. A `signal_quality` below 0.60 means the device does not trust its own reading, so neither does the program.
4. Rows for one session may be spread across several files; they are grouped by `session_id` whichever file they came from, and the report names the sources.
5. `activity_level` and `signal_quality` have no personal baseline in the participant file, so they are summarised but not compared.

**Known limitations**

1. **The limits are fixed for everybody.** They suit this data. Real athletes, children, or people on heart medication would need personal limits, for example derived from maximum heart rate rather than resting heart rate.
2. **One verdict per session.** A session with a warm up, intervals and a cool down receives a single label. A real product would classify segments and show the shape of the session.
3. **Rejecting the whole row is strict.** A row with a sound heart rate but a missing temperature is refused completely, even though part of it is usable. The alternative, partial rows, would make every average quietly depend on which fields happened to survive.
4. **The recovery rule needs the peak inside the file.** A cool down exported on its own, with the hard part in another file, looks like a slow session rather than a recovery.
5. **Simulated data only.** The program has never met a real wearable, where faults are messier and arrive in patterns rather than one per row.

## 17. Where each requirement is met

| Requirement | Where |
|---|---|
| Load the profile file | `loading.load_participants` |
| Load both the valid and the invalid session files | `loading.load_sessions`, default in `cli` |
| `open(..., encoding="utf-8", newline="")` and the `csv` module | `loading._open_csv`, `csv.reader` throughout |
| Convert values to suitable types | `validation.to_int`, `validation.to_float` |
| Group records by session identifier | `loading._handle_row`, `models.Session` |
| Connect each session to an existing participant | `loading._inspect_row`, the `KeyError` branch |
| At least two regular-expression validations, anchored or full match | `validation`, section 9 |
| Missing fields and unexpected row lengths | `loading._inspect_row`, `_measurement_problems` |
| Reject values of the wrong type | `validation.to_int`, `to_float` |
| Reject impossible or out of range measurements | `validation.require_range`, `Observation.RANGE_CHECKS` |
| Reject unknown participants | `loading._inspect_row` |
| A documented signal quality rule | section 10 |
| Record file, row number, field and reason for every rejected row | `loading.Rejection`, `rejected_records.txt` |
| At least two custom exception classes, raised and handled | `errors`, four classes, section 8 |
| At least three targeted try and except structures | 25 of them, section 8 |
| `FileNotFoundError`, `PermissionError`, `ValueError`, `KeyError`, csv errors | section 8 |
| No empty `except`, no `except Exception` as the strategy | section 8 |
| Reuse and improve the analysis from Assignment I | `analysis`, `rules`, section 11 |
| Distinguish insufficient data from a real result | `InsufficientDataRule`, priority 1 |
| Create the output directory when it does not exist | `reporting.ensure_output_directory` |
| `analysis_summary.csv`, `analysis_report.txt`, `rejected_records.txt` | `reporting`, section 12 |
| Predictable output when run again | section 12, `test_running_twice_produces_identical_files` |
| A package with at least three meaningful modules | nine modules, section 5 |
| Classes, encapsulation, composition | section 6 |
| `pathlib` for file paths | every module that touches a path |
| A structured result as a dictionary or domain object | `SessionAnalyzer.analyze` |
| Tests for valid, invalid, missing file and boundary cases | `tests.py`, section 14 |
| Standard library only | `requirements.txt`, section 2 |
| Runs from the repository root, no absolute paths | section 3 |
| A completion summary of accepted rows, rejected rows and report files | `cli._completion_summary` |

## 18. Summary

Assignment I asked whether a program could judge a training session against a person's own normal. This one asks whether it can keep doing that when the file it is handed is imperfect, and the answer runs through every part of the design: **read what you can, refuse what you cannot, and write down exactly why.**

That single principle explains the shape of the whole program. It is why the loader collects every problem in a row instead of stopping at the first. It is why there are three exception types rather than one, so a broken row and a broken file can be told apart. It is why a session whose every row failed still appears in the report. And it is why the output is identical on the second run: a report you cannot trust to say the same thing twice is not a report.

A question to leave with you. The program currently treats a rejected row as a loss, something to be counted and explained. But five rejections in a row, all for low signal quality, all from the same participant, are not really five independent faults; they are one loose strap, and a trainer would want to be told that in those words. Which part of this design would you change first to let the program notice a *pattern* in its own rejections, rather than only a list of them?
