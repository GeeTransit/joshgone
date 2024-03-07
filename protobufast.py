"""Skim Protobuf fast

The encoding format is described here:
https://protobuf.dev/programming-guides/encoding/

The main idea for this module is to make it possible to skip as much as
possible. This means that only the size of each field is decoded - the user can
decode the actual field if they wish.

A side effect of this design is that the schema is implicitly defined by the
user's code. This improves performance at the cost of readability. In the
future I may make it possible to have a simple schema to make reading nested
fields easier.

Example:
    data = open(..., mode="rb").read()
    for i, wire_type, field, value in skim(data, 0, len(data)):
        if wire_type == 0:  # VARINT
            print(f'{field}:VARINT {value}')
        elif wire_type == 1:
            print(f'{field}:I64 {int.from_bytes(data[value:i], "little")}i64')
        elif wire_type == 2:
            print(f'{field}:LEN {i-value}')
        elif wire_type == 3:
            print(f'{field}:GROUP {i-value}')
        elif wire_type == 4:
            print(f'{field}:EGROUP')
        elif wire_type == 5:
            print(f'{field}:I32 {int.from_bytes(data[value:i], "little")}i32')

"""
import struct
from typing import Any, Tuple, Iterator

def read_varint(data: bytes, i: int) -> Tuple[int, int]:
    k = r = 0
    while True:
        d = data[i]
        r += (d & 0x7F) << k
        i += 1
        if d < 128:
            return i, r
        k += 7

def read_tag(data: bytes, i: int) -> Tuple[int, int, int]:
    i, tag = read_varint(data, i)
    wire_type = tag & 0x07
    field = tag >> 3
    return i, field, wire_type

def read(data: bytes, i: int) -> Tuple[int, int, int, int]:
    i, field, wire_type = read_tag(data, i)

    if wire_type == 2:  # LEN
        i, length = read_varint(data, i)
        return i + length, 2, field, i

    elif wire_type == 0:  # VARINT
        i, number = read_varint(data, i)
        return i, 0, field, number

    elif wire_type == 5:  # I32
        return i + 4, 5, field, i

    elif wire_type == 1:  # I64
        return i + 8, 1, field, i

    elif wire_type == 3:  # SGROUP
        start = i
        while wire_type != 4:
            i, wire_type, _, _ = read(data, i)
        return i, 3, field, start

    elif wire_type == 4:  # EGROUP
        return i, 4, -1, -1

    else:
        raise ValueError(f'unknown wire type: {wire_type}')

def skim(data: bytes, i: int, j: int) -> Iterator[Tuple[int, int, int, int]]:
    while i < j:
        x = read(data, i)
        yield x
        i = x[0]

def to_float(data: bytes, i: int, j: int) -> float:
    assert i + 4 == j
    return struct.unpack("<f", data[i:j])[0]

def to_double(data: bytes, i: int, j: int) -> float:
    assert i + 8 == j
    return struct.unpack("<d", data[i:j])[0]

def to_sint(data: bytes, i: int, j: int) -> int:
    if i & 1:
        return ~i >> 1
    return i >> 1

