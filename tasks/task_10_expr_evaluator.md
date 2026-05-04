# Task: Fix Multi-File Expression Evaluator

## User Persona

- **High-level goals:** Building a sandboxed arithmetic expression evaluator. It must match Python's semantics exactly.
- **Familiarity with tools:** Strong Python developer who knows that `//` floors toward negative infinity and that `**` is right-associative. Will notice immediately if `2^3^2` gives 64 instead of 512.
- **Communication style:** Quotes specific expressions and their expected vs actual results: "`-7 // 2` should give -4, not -3."
- **Patience style:** One shot per bug. Won't accept partial fixes.
- **Hint policy:** Tells you which expression is wrong and what the expected value is. Will not name which file.

## Context

Three files: `lexer.py`, `parser.py`, `evaluator.py`. Tests: `tests/test_evaluator.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Unary Minus

**Initial Prompt:**

> "My evaluator crashes on `-5` with a ParseError. It should return -5. Fix it — don't touch the test file."

**Planned Interactions:**

- Clarification answers:
  - If agent asks which file: "Look at the parser."
  - If agent asks about unary vs binary minus: "Unary minus should work in any position: `-5`, `-3 + 10`, `--4`, `-(3+4)`."
- Corrections and hints:
  - If agent modifies the lexer instead of the parser: "The lexer is fine — MINUS is already tokenized. The issue is in the parse tree."

**Completion Criteria:**

`pytest tests/test_evaluator.py::TestUnaryMinus -x -q` passes all 5 tests.

---

### Milestone 2: Fix Power Operator Associativity

**Initial Prompt:**

> "`2^3^2` gives 64 but should give 512. Power must be right-associative: `2^3^2 = 2^(3^2) = 512`. Fix it."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about precedence vs associativity: "The precedence is correct (power binds tighter than multiply). Only the associativity within a chain of `^` operators is wrong."
- Corrections and hints:
  - If agent changes the wrong thing: "After your change, `2^3` should still be 8 and `2^3^2` should be 512."

**Completion Criteria:**

`pytest tests/test_evaluator.py::TestPower -x -q` passes all tests.

---

### Milestone 3: Fix Floor Division

**Initial Prompt:**

> "`-7 // 2` gives -3 but should give -4. Python's `//` always floors toward negative infinity. Fix the evaluator."

**Planned Interactions:**

- Clarification answers:
  - If agent asks which file: "The evaluator — not the parser."
  - If agent asks: "Yes `7 // -2` should also be -4, and `-7 // -2` should be 3."
- Corrections and hints:
  - If agent uses `int(-7/2)`: "That still truncates toward zero. Python's `math.floor` or the `//` operator itself gives the right answer."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests across all three test classes.
