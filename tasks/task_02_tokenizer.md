# Task: Fix Python-Like Source Tokenizer

## User Persona

- **High-level goals:** Building a lightweight Python linter/formatter. Needs a tokenizer that correctly handles all Python string literal forms and produces accurate line/column positions.
- **Familiarity with tools:** Strong Python developer, has read CPython's `tokenize` module source before. Expects the tokenizer to follow Python semantics exactly where documented.
- **Communication style:** Specific about what failed: "raw string `r\"\\n\"` should NOT interpret the escape sequence but the tokenizer gives me a newline character."
- **Patience style:** Will test each fix independently. One missed edge case = another round.
- **Hint policy:** Will reference CPython tokenize docs. Will not write code.

## Context

Implementation: `tokenizer.py`. Tests: `tests/test_tokenizer.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix String Escape Processing

**Initial Prompt:**

> "The tokenizer produces STRING tokens with the raw source form including quotes, but it should produce the *interpreted* string value — quotes stripped, escape sequences processed. So `\"hello\\nworld\"` should give a token with value `hello\nworld`, not `\"hello\\nworld\"`. Fix `tokenizer.py`. Tests are in `TestStrings`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about escape sequences to support: "At minimum: `\\n`, `\\t`, `\\r`, `\\\\`, `\\'`, `\\\"`, `\\a`, `\\b`, `\\f`, `\\v`, `\\0`. The `_ESCAPE_MAP` in the file already lists them."
- Corrections and hints:
  - If agent strips quotes but doesn't process escapes: "`test_escape_newline` still fails — the value needs to be the interpreted string."
  - If agent processes escapes but uses `bytes.decode('unicode_escape')`: "That approach has encoding issues for non-ASCII — process the escape map directly."

**Completion Criteria:**

`pytest tests/test_tokenizer.py::TestStrings::test_double_quoted_string_value tests/test_tokenizer.py::TestStrings::test_escape_newline tests/test_tokenizer.py::TestStrings::test_escape_tab tests/test_tokenizer.py::TestStrings::test_escaped_backslash -x -q` all pass.

---

### Milestone 2: Add Raw String Support

**Initial Prompt:**

> "Now add support for raw strings (`r\"...\"` and `r'...'`). In a raw string, backslash sequences are NOT interpreted — `r\"\\n\"` should produce the two-character string backslash-n, not a newline. See `test_raw_string_no_escape_processing` and `test_raw_string_single_quote`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about `rb\"...\"`/`br\"...\"` (raw bytes): "Not needed for this task, just `r\"...\"` and `r'...'`."
- Corrections and hints:
  - If agent handles `r\"\"\"...\"\"\"` triple raw but forgets single-quoted raw: "`test_raw_string_single_quote` still fails."
  - If agent's regex eats the `r` prefix but then still processes escapes: "You need to check the prefix *before* deciding whether to run escape processing."

**Completion Criteria:**

`pytest tests/test_tokenizer.py::TestStrings -x -q` passes all string tests including raw string tests.

---

### Milestone 3: Add Triple-Quoted String Support

**Initial Prompt:**

> "Last piece: triple-quoted strings — `\"\"\"...\"\"\"` and `'''...'''` — that can span multiple lines. The content between the triple delimiters (including newlines) becomes the token value. `r\"\"\"...\"\"\"` should also work (no escape processing). See `test_triple_double_quoted`, `test_triple_single_quoted`, `test_triple_raw_string`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks how to update the regex: "You'll need to handle triple-quoted strings *before* single-quoted in the pattern (longer alternative first). Greedy vs non-greedy matters."
- Corrections and hints:
  - If line numbers are wrong after a triple-quoted string: "A multi-line string spans multiple lines — make sure `line_num` is updated for each `\\n` inside it."
  - If the regex is catastrophically backtracking: "Use a non-greedy `.*?` with `re.DOTALL` for the triple-quoted body."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests (TestBasic, TestStrings, TestIndentation, TestLineCol).
