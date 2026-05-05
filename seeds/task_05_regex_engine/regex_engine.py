"""
NFA-based regex engine using Thompson's construction.

Supports:
  .   any character
  *   zero or more (Kleene star, greedy)
  +   one or more
  ?   zero or one
  |   alternation
  ()  grouping
  [abc]  character class
  [^abc] negated character class
  \\d \\w \\s escape sequences

Does NOT support backreferences, lookahead, or anchors (^/$).

Based on: Russ Cox "Regular Expression Matching Can Be Simple And Fast"
https://swtch.com/~rsc/regexp/regexp1.html

Public API:
    engine = RegexEngine()
    m = engine.match("a*b", "aaab")   # → Match(start=0, end=4) or None
    m = engine.match("a|b", "b")      # → Match(start=0, end=1)
    m = engine.findall("\\d+", "a1b2") # → ["1", "2"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Match:
    start: int
    end: int
    string: str

    def group(self) -> str:
        return self.string[self.start:self.end]


# ── NFA state machine ─────────────────────────────────────────────────────────

EPSILON = object()   # sentinel for ε-transitions
ANY = object()       # matches any char (dot)
MATCH = object()     # accepting state marker


@dataclass
class State:
    transition: object = None    # char, EPSILON, ANY, MATCH, or lambda(c)->bool
    out1: Optional["State"] = None
    out2: Optional["State"] = None   # second output for splits (|, *, etc.)

    def is_match(self) -> bool:
        return self.transition is MATCH


@dataclass
class Fragment:
    """Partially-built NFA with a start state and list of dangling output slots."""
    start: State
    outs: list   # list of (state, attr) tuples pointing to unconnected outputs


def _patch(outs: list, s: State) -> None:
    """Connect all dangling outputs in *outs* to state *s*."""
    for state, attr in outs:
        setattr(state, attr, s)


def _compile(pattern: str) -> tuple[State, State]:
    """
    Compile pattern to NFA. Returns (start_state, match_state).

    BUG A: The ε-closure computation in _e_closure does not correctly handle
    states that have BOTH out1 and out2 as ε-transitions. Specifically, when
    a split state is visited, only out1 is followed if out2 is also epsilon —
    this breaks alternation (|) and optional (?).

    BUG B: Character class parsing [abc] doesn't handle the hyphen range [a-z]
    correctly — it treats '-' as a literal character rather than a range indicator.
    So [a-z] would only match 'a', '-', or 'z' instead of any lowercase letter.
    """
    tokens = _tokenize(pattern)
    stack: list[Fragment] = []
    i = 0

    while i < len(tokens):
        tok = tokens[i]
        i += 1

        if tok == '(':
            # Find matching )
            depth = 1
            j = i
            while j < len(tokens) and depth > 0:
                if tokens[j] == '(':
                    depth += 1
                elif tokens[j] == ')':
                    depth -= 1
                j += 1
            sub_start, sub_match = _compile(''.join(tokens[i:j-1]))
            sub_match.transition = None   # make it non-matching for now
            frag = Fragment(sub_start, [(sub_match, 'out1')])
            stack.append(frag)
            i = j
            # Handle postfix operators
            if i < len(tokens) and tokens[i] in ('*', '+', '?'):
                _apply_postfix(stack, tokens[i])
                i += 1

        elif tok == '[':
            # Character class
            j = i
            negated = False
            if j < len(tokens) and tokens[j] == '^':
                negated = True
                j += 1
            chars = set()
            while j < len(tokens) and tokens[j] != ']':
                c = tokens[j]
                # BUG B: range handling — should check if tokens[j+1] == '-' and tokens[j+2] exists
                # Current: treats each char literally, '-' included
                chars.add(c)
                j += 1
            char_set = frozenset(chars)
            if negated:
                fn = lambda c, cs=char_set: c not in cs
            else:
                fn = lambda c, cs=char_set: c in cs
            s = State(transition=fn)
            stack.append(Fragment(s, [(s, 'out1')]))
            i = j + 1   # skip ']'
            if i < len(tokens) and tokens[i] in ('*', '+', '?'):
                _apply_postfix(stack, tokens[i])
                i += 1

        elif tok in ('*', '+', '?', '|'):
            if tok == '|':
                if len(stack) >= 2:
                    e2 = stack.pop()
                    e1 = stack.pop()
                    split = State(transition=EPSILON, out1=e1.start, out2=e2.start)
                    stack.append(Fragment(split, e1.outs + e2.outs))
            else:
                _apply_postfix(stack, tok)

        else:
            # Literal character or escape
            if tok == '.':
                s = State(transition=ANY)
            elif tok.startswith('\\'):
                escape = tok[1]
                if escape == 'd':
                    fn = str.isdigit
                elif escape == 'w':
                    fn = lambda c: c.isalnum() or c == '_'
                elif escape == 's':
                    fn = str.isspace
                else:
                    ch = escape
                    fn = lambda c, _c=ch: c == _c
                s = State(transition=fn)
            else:
                ch = tok
                s = State(transition=lambda c, _c=ch: c == _c)
            stack.append(Fragment(s, [(s, 'out1')]))
            # Check for postfix operator
            if i < len(tokens) and tokens[i] in ('*', '+', '?'):
                _apply_postfix(stack, tokens[i])
                i += 1

    # Concatenate all fragments on stack
    if not stack:
        match_state = State(MATCH)
        return match_state, match_state

    result = stack[0]
    for frag in stack[1:]:
        # Concatenate: patch first frag's outs to second frag's start
        _patch(result.outs, frag.start)
        result = Fragment(result.start, frag.outs)

    match_state = State(MATCH)
    _patch(result.outs, match_state)
    return result.start, match_state


def _apply_postfix(stack: list, op: str) -> None:
    e = stack.pop()
    if op == '*':
        split = State(transition=EPSILON, out1=e.start, out2=None)
        _patch(e.outs, split)
        stack.append(Fragment(split, [(split, 'out2')]))
    elif op == '+':
        split = State(transition=EPSILON, out1=e.start, out2=None)
        _patch(e.outs, split)
        stack.append(Fragment(e.start, [(split, 'out2')]))
    elif op == '?':
        split = State(transition=EPSILON, out1=e.start, out2=None)
        stack.append(Fragment(split, e.outs + [(split, 'out2')]))


def _tokenize(pattern: str) -> list[str]:
    tokens = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == '\\' and i + 1 < len(pattern):
            tokens.append(c + pattern[i + 1])
            i += 2
        else:
            tokens.append(c)
            i += 1
    return tokens


# ── simulation ────────────────────────────────────────────────────────────────

def _e_closure(states: set[State]) -> set[State]:
    """
    Compute ε-closure: all states reachable from *states* via ε-transitions.

    BUG A: When a state has transition=EPSILON, we should follow BOTH out1
    and out2 (it's a split state for alternation). Current code only follows
    out1 if the state has EPSILON transition, ignoring out2. This breaks
    patterns like "a|b" where the split state has out1→a-path and out2→b-path.
    """
    closure = set(states)
    worklist = list(states)
    while worklist:
        s = worklist.pop()
        if s.transition is EPSILON:
            if s.out1 and s.out1 not in closure:
                closure.add(s.out1)
                worklist.append(s.out1)
            # BUG A: missing: follow out2 as well for split states
            # if s.out2 and s.out2 not in closure:
            #     closure.add(s.out2)
            #     worklist.append(s.out2)
    return closure


def _step(states: set[State], char: str) -> set[State]:
    """Advance all states by consuming *char*."""
    next_states = set()
    for s in states:
        t = s.transition
        if t is EPSILON or t is MATCH or t is None:
            continue
        if t is ANY:
            if s.out1:
                next_states.add(s.out1)
        elif callable(t):
            if t(char) and s.out1:
                next_states.add(s.out1)
    return next_states


def _simulate(start: State, text: str, pos: int) -> Optional[int]:
    """
    Try to match from position *pos*. Returns end position on match, else None.
    """
    current = _e_closure({start})
    if any(s.is_match() for s in current):
        return pos   # empty match

    end = None
    for i, char in enumerate(text[pos:], pos):
        current = _e_closure(_step(current, char))
        if any(s.is_match() for s in current):
            end = i + 1
        if not current:
            break
    return end


# ── public API ────────────────────────────────────────────────────────────────

class RegexEngine:
    def match(self, pattern: str, text: str) -> Optional[Match]:
        """Try to match pattern anywhere in text. Returns first match or None."""
        start_state, _ = _compile(pattern)
        for i in range(len(text) + 1):
            end = _simulate(start_state, text, i)
            if end is not None:
                return Match(i, end, text)
        return None

    def fullmatch(self, pattern: str, text: str) -> Optional[Match]:
        """Return a Match only if the ENTIRE text matches pattern."""
        m = self.match('^' + pattern, text)   # anchoring via convention
        # Actually just check if match spans full string
        start_state, _ = _compile(pattern)
        end = _simulate(start_state, text, 0)
        if end == len(text):
            return Match(0, len(text), text)
        return None

    def findall(self, pattern: str, text: str) -> list[str]:
        """Return all non-overlapping matches."""
        start_state, _ = _compile(pattern)
        results = []
        i = 0
        while i <= len(text):
            end = _simulate(start_state, text, i)
            if end is not None and end > i:
                results.append(text[i:end])
                i = end
            else:
                i += 1
        return results
