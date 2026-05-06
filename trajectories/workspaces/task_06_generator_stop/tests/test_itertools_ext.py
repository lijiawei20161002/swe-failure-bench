"""
Tests for itertools_ext.
Run: pip install pytest && pytest tests/ -x -q
"""
import pytest
from itertools_ext import chunked, sliding_window, interleave, take_while_inclusive, flatten


class TestChunked:
    def test_evenly_divisible(self):
        assert list(chunked(range(6), 2)) == [[0, 1], [2, 3], [4, 5]]

    def test_last_chunk_partial(self):
        """
        When the iterable length is not divisible by size, the last chunk
        must contain the remaining elements — not be silently dropped.

        This is the core bug: calling next() inside a generator body raises
        StopIteration when the iterator is exhausted. Since PEP 479 (Python
        3.7+), StopIteration raised inside a generator is converted to
        RuntimeError: generator raised StopIteration.

        Symptom: list(chunked([1,2,3,4,5], 2)) raises RuntimeError instead
        of returning [[1,2],[3,4],[5]].

        Fix: replace `next(it)` with an explicit try/except StopIteration
        and break, or use itertools.islice:
            while chunk := list(itertools.islice(it, size)):
                yield chunk
        """
        result = list(chunked([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]], (
            f"Expected [[1,2],[3,4],[5]], got {result}. "
            "chunked() must yield a final partial chunk when the iterable "
            "length is not evenly divisible by size."
        )

    def test_single_element_iterable(self):
        assert list(chunked([42], 3)) == [[42]]

    def test_exactly_one_chunk(self):
        assert list(chunked([1, 2, 3], 3)) == [[1, 2, 3]]

    def test_size_one(self):
        assert list(chunked([10, 20, 30], 1)) == [[10], [20], [30]]

    def test_empty_iterable(self):
        assert list(chunked([], 4)) == []

    def test_large_size(self):
        """size larger than iterable → one partial chunk."""
        assert list(chunked([1, 2], 10)) == [[1, 2]]

    def test_generator_input(self):
        result = list(chunked((x * x for x in range(7)), 3))
        assert result == [[0, 1, 4], [9, 16, 25], [36]]

    def test_invalid_size(self):
        with pytest.raises(ValueError):
            list(chunked([1, 2], 0))

    def test_chunk_elements_correct(self):
        data = list(range(100))
        chunks = list(chunked(data, 7))
        # Flatten and compare
        reconstructed = [item for chunk in chunks for item in chunk]
        assert reconstructed == data

    def test_no_data_loss(self):
        """Every element must appear in exactly one chunk."""
        data = list(range(13))
        chunks = list(chunked(data, 4))
        flat = [x for chunk in chunks for x in chunk]
        assert flat == data
        assert len(chunks) == 4   # ceil(13/4) = 4

    def test_string_chunking(self):
        result = list(chunked("ABCDE", 2))
        assert result == [["A", "B"], ["C", "D"], ["E"]]


class TestSlidingWindow:
    def test_basic(self):
        result = list(sliding_window("ABCDE", 3))
        assert result == [("A","B","C"), ("B","C","D"), ("C","D","E")]

    def test_window_equals_length(self):
        result = list(sliding_window([1, 2, 3], 3))
        assert result == [(1, 2, 3)]

    def test_window_larger_than_iterable(self):
        result = list(sliding_window([1, 2], 5))
        assert result == []

    def test_window_of_one(self):
        result = list(sliding_window([1, 2, 3], 1))
        assert result == [(1,), (2,), (3,)]

    def test_empty(self):
        assert list(sliding_window([], 3)) == []


class TestInterleave:
    def test_basic(self):
        result = list(interleave([1, 2, 3], ["a", "b", "c"]))
        assert result == [1, "a", 2, "b", 3, "c"]

    def test_stops_at_shortest(self):
        result = list(interleave([1, 2, 3], ["a", "b"]))
        assert result == [1, "a", 2, "b"]

    def test_single_iterable(self):
        assert list(interleave([1, 2, 3])) == [1, 2, 3]

    def test_empty_iterable(self):
        assert list(interleave([], [1, 2])) == []


class TestTakeWhileInclusive:
    def test_includes_first_failing(self):
        result = list(take_while_inclusive(lambda x: x < 5, range(10)))
        assert result == [0, 1, 2, 3, 4, 5]

    def test_all_pass(self):
        result = list(take_while_inclusive(lambda x: x < 100, range(5)))
        assert result == [0, 1, 2, 3, 4]

    def test_first_fails(self):
        result = list(take_while_inclusive(lambda x: x > 0, [0, 1, 2]))
        assert result == [0]

    def test_empty(self):
        assert list(take_while_inclusive(lambda x: True, [])) == []


class TestFlatten:
    def test_one_level(self):
        assert list(flatten([[1, 2], [3, 4]])) == [1, 2, 3, 4]

    def test_deep(self):
        assert list(flatten([[1, [2, [3]]]])) == [1, 2, 3]

    def test_depth_limit(self):
        assert list(flatten([[1, [2, [3]]]], depth=1)) == [1, [2, [3]]]

    def test_strings_not_flattened(self):
        assert list(flatten(["abc", [1, 2]])) == ["abc", 1, 2]

    def test_empty(self):
        assert list(flatten([])) == []
