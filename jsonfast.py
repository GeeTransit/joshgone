"""Skim JSON fast

The encoding format is described here:
https://www.json.org/json-en.html

This module is inspired by ``protobufast.py`` where we try to skip as much
decoding work as possible. Only the size of each expression is decoded - the
user can decode the actual expression if they wish.

Example:
    >>> data = b' 123 "def" { "x" : [ 3.5 ] } [ true , { "a": null } ] false '
    >>> # Note: ensure there is whitespace after all data
    >>> last_i = 0
    >>> for i, first_char, start in skim(data, 0, len(data)):
    ...     if first_char == b'"'[0]:  # string
    ...         print(repr(to_str(data, start, i)))
    ...     elif first_char == b"{"[0]:  # object
    ...         # note that start points to the first item
    ...         print(data[last_i:i].strip().decode())
    ...     elif first_char == b"["[0]:  # array
    ...         # note that start points to the first item
    ...         print(data[last_i:i].strip().decode())
    ...     elif first_char in b"1234567890-":  # numbers
    ...         print(to_num(data, start, i))
    ...     elif first_char in b"tfn":  # true false null
    ...         print(data[start-1:i].strip().decode())
    ...     elif first_char in b",:}]":  # , : } ]
    ...         print(chr(first_char))
    ...     last_i = i
    23.0
    'def'
    { "x" : [ 3.5 ] }
    [ true , { "a": null } ]
    false

"""
import re
from typing import Any, Tuple, Iterator

def read_whitespace(data: bytes, i: int) -> int:
    while data[i] in b" \t\n\r":
        i += 1
    return i

def read_char(data: bytes, i: int) -> Tuple[int, int]:
    return i+1, data[i]

def read_alpha(data: bytes, i: int) -> int:
    while b"a"[0] <= data[i] <= b"z"[0]:
        i += 1
    return i

_read_num_set = frozenset(b"1234567890-.eE+")
def read_num(data: bytes, i: int) -> int:
    _num_set = _read_num_set
    while data[i] in _num_set:
        i += 1
    return i

def read_str(data: bytes, i: int) -> int:
    while True:
        i = data.index(b'"'[0], i) + 1
        if data[i-2] != b"\\"[0]:
            break
    return i

_READ_NESTED_PATTERN = re.compile(br'[^][{}"]*(?:"(?:\\.|[^\\"])*"[^][{}"]*)*')
def part_nested(data: bytes, i: int, stack: bytearray) -> Tuple[int, bytearray]:
    _nested_pattern = _READ_NESTED_PATTERN
    if stack and stack[-1] == b'"'[0]:
        while True:
            i = data.find(b'"'[0], i) + 1
            if i == -1:
                return len(data), stack
            if data[i-2] != b"\\"[0]:
                break
        stack.pop()
    while stack:
        i = _nested_pattern.match(data, i).end()
        if i == len(data):
            break
        if data[i] == stack[-1]:
            stack.pop()
        else:
            assert data[i] in b'{["'
            stack.append(b'"'[0] if data[i] == b'"'[0] else data[i]+2)
        i += 1
    return i, stack

def read_array(data: bytes, i: int) -> int:
    i, stack = part_nested(data, i, bytearray(b"]"))
    if stack:
        raise IndexError("array not closed within given data")
    return i

def read_object(data: bytes, i: int) -> int:
    i, stack = part_nested(data, i, bytearray(b"}"))
    if stack:
        raise IndexError("object not closed within given data")
    return i

def read_tag(data: bytes, i: int) -> int:
    i = read_whitespace(data, i)
    return read_char(data, i)

def read_no_end(data: bytes, i: int) -> Tuple[int, int]:
    i, first_char = read_tag(data, i)
    if first_char == b'"'[0]:  # string
        pass
    elif first_char == b"{"[0]:  # object
        i = read_whitespace(data, i)
    elif first_char == b"["[0]:  # array
        i = read_whitespace(data, i)
    elif first_char in b"1234567890-":  # numbers
        pass
    elif first_char in b"tfn":  # true false null
        pass
    elif first_char in b",:}]":  # , : } ]
        pass
    else:
        raise ValueError(f'unknown first char: {repr(first_char)}')
    return i, first_char

def read(data: bytes, i: int) -> Tuple[int, int, int]:
    i, first_char = read_no_end(data, i)
    if first_char == b'"'[0]:  # string
        end = read_str(data, i)
    elif first_char == b"{"[0]:  # object
        end = read_object(data, i)
    elif first_char == b"["[0]:  # array
        end = read_array(data, i)
    elif first_char in b"1234567890-":  # numbers
        end = read_num(data, i)
    elif first_char in b"tfn":  # true false null
        end = read_alpha(data, i)
    elif first_char in b",:}]":  # , : } ]
        end, i = i, -1
    else:
        raise ValueError(f'unknown first char: {repr(first_char)}')
    return end, first_char, i

def skim_array(data: bytes, i: int, j: int) -> Iterator[Tuple[int, int, int]]:
    """Returns an iterable of `read`-able ranges

    Example:
        >>> data = b' [ 123 , "def" , { "x" : [ 3.5 ] } ] '
        >>> i, first_char, start = read(data, 0)
        >>> assert first_char == b"["[0]
        >>> parts = list(skim_array(data, start, i))
        >>> [data[i:read(data, i)[0]].strip() for _, _, i in parts]
        [b'123', b'"def"', b'{ "x" : [ 3.5 ] }']

    """
    while i < j:
        start = i
        i, first_char, _ = read(data, i)
        assert first_char not in b",]", first_char
        i, split_char = read_tag(data, i)
        assert split_char in b",:]}", split_char
        yield i, first_char, start
        if split_char == b"]}"[0]:
            break

def skim_object(data: bytes, i: int, j: int) -> Iterator[Tuple[int, int, int]]:
    """Returns an iterable of `skim_array`-able ranges

    Example:
        >>> data = b' { "a": 123 , "b": "def" , "c": { "x" : [ 3.5 ] } } '
        >>> i, first_char, start = read(data, 0)
        >>> assert first_char == b"{"[0]
        >>> pairs = list(skim_object(data, start, i))
        >>> parts = [v for i, _, j in pairs for v in skim_array(data, j, i)]
        >>> [data[i:read(data, i)[0]].strip() for _, _, i in parts]
        [b'"a"', b'123', b'"b"', b'"def"', b'"c"', b'{ "x" : [ 3.5 ] }']

    """
    while i < j:
        start = i
        i, key_char, _ = read(data, i)
        assert key_char == b'"'[0], key_char
        i, split_char = read_tag(data, i)
        assert split_char == b":"[0], split_char
        i, first_char, _ = read(data, i)
        assert first_char not in b",}", first_char
        i, split_char = read_tag(data, i)
        assert split_char in b"},", split_char
        yield i, first_char, start
        if split_char == b"}"[0]:
            break

def skim(data: bytes, i: int, j: int) -> Iterator[Tuple[int, int, int]]:
    while i < j:
        x = read(data, i)
        yield x
        i = x[0]
        try:
            i = read_whitespace(data, i)
        except IndexError:
            break

def to_str(data: bytes, i: int, j: int) -> str:
    return data[i:j-1].decode("unicode_escape")

def to_num(data: bytes, i: int, j: int) -> float:
    return float(data[i:j].decode())
