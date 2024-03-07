import argparse
import sys
import json
import asyncio
import enum
import re
import base64
from typing import Optional, Iterable
from dataclasses import dataclass, fields

import httpx
from pure_protobuf.dataclasses_ import field, optional_field, message
from pure_protobuf.types import int32

import protobufast as pf

# - Protobuf schemas
# Converted from https://onlinesequencer.net/sequence.proto and
# https://onlinesequencer.net/note_type.proto

# C0 = 0, CS0 = 1, ..., B8 = 107
NoteType = enum.IntEnum(
    "NoteType",
    [
        f"{note}{octave}"
        for octave in range(9)
        for note in "C CS D DS E F FS G GS A AS B".split()
    ],
    start=0,
)

@message
@dataclass
class Note:
    type: NoteType = field(1, default=NoteType.C0)
    time: float = field(2, default=0.0)
    length: float = field(3, default=0.0)
    instrument: int32 = field(4, default=0)
    volume: float = field(5, default=0.0)

@message
@dataclass
class Marker:
    time: float = field(1, default=0.0)
    setting: int32 = field(2, default=0)
    instrument: int32 = field(3, default=0)
    value: float = field(4, default=0.0)
    blend: bool = field(5, default=False)

@message
@dataclass
class InstrumentSettings:
    volume: float = field(1, default=0.0)
    delay: bool = field(2, default=False)
    reverb: bool = field(3, default=False)
    pan: float = field(4, default=0.0)
    enable_eq: bool = field(5, default=False)
    eq_low: float = field(6, default=0.0)
    eq_mid: float = field(7, default=0.0)
    eq_high: float = field(8, default=0.0)
    detune: float = field(9, default=0.0)

@message
@dataclass
class InstrumentSettingsPair:
    key: Optional[int32] = optional_field(1)
    value: Optional[InstrumentSettings] = optional_field(2)

@message
@dataclass
class SequenceSettings:
    bpm: int32 = field(1, default=0)
    time_signature: int32 = field(2, default=0)
    # Maps aren't implemented in pure_protobuf yet but we can still parse them
    # thanks to
    # https://developers.google.com/protocol-buffers/docs/proto3#backwards_compatibility
    instruments: list[InstrumentSettingsPair] = field(3, default_factory=list)
    # Storing volume as (1 - volume) so it defaults to volume=1.
    one_minus_volume: float = field(4, default=0.0)

@message
@dataclass
class Sequence:
    settings: SequenceSettings = field(1, default_factory=SequenceSettings)
    notes: list[Note] = field(2, default_factory=list)
    markers: list[Marker] = field(3, default_factory=list)

# - Helpers

def _extract_data(text):
    """Extracts the base64 encoded string from the site's JavaScript"""
    # This is more fragile than a nuclear bomb
    return base64.b64decode(re.search(r"var data = '([^']*)';", text)[1])

def _int_or_float(num):
    if num % 1 == 0:
        return round(num)
    return num

def _field_num_of(cls, name: str) -> int:
    for field in fields(cls):
        if field.name == name:
            return field.metadata["number"]
    raise AttributeError(f'no message field named: {name}')

def _skim_field(field: int, msgs: Iterable) -> Iterable:
    for msg in msgs:
        if msg[2] == field:
            yield msg

def _last_field(field: int, msgs: Iterable):
    msg = None
    for msg in _skim_field(field, msgs):
        pass
    return msg

def _get_notes(data) -> Iterable[dict]:
    """Converts raw song data into a sorted iterable of notes"""
    settings_num = _field_num_of(Sequence, "settings")
    settings = SequenceSettings.loads(b"".join(
        data[msg[3]:msg[0]]
        for msg in _skim_field(settings_num, pf.skim(data, 0, len(data)))
    ))
    song = Sequence()
    song.settings = settings

    bpm = song.settings.bpm
    all_volume = 1 - song.settings.one_minus_volume
    # Convert to a dict for constant instrument settings retrieval
    instrument_settings = {
        kv.key: kv.value
        for kv in song.settings.instruments
        if kv.key is not None and kv.value is not None
    }

    # Sort note messages by time (without loading all fields of a note)
    notes_num = _field_num_of(Sequence, "notes")
    time_num = _field_num_of(Note, "time")
    def msg_note_time(msg):
        time_msg = _last_field(time_num, pf.skim(data, msg[3], msg[0]))
        if time_msg is None:
            return 0.0
        assert time_msg[1] == 5
        return pf.to_float(data, time_msg[3], time_msg[0])
    note_msgs = sorted(
        _skim_field(notes_num, pf.skim(data, 0, len(data))),
        key=msg_note_time,
    )

    # Return a iterator of note infos sorted by time
    first = True
    for msg in note_msgs:
        note = Note.loads(data[msg[3]:msg[0]])
        note_info = {
            "instrument": note.instrument,
            "type": note.type.name.replace("S", "#"),
            "time": _int_or_float(note.time * (60/bpm/4)),
            "length": _int_or_float(note.length * (60/bpm/4)),
            "volume": _int_or_float(
                note.volume
                * all_volume
                * (
                    instrument_settings[note.instrument].volume
                    if note.instrument in instrument_settings
                    else 1
                )
            ),
            "detune": _int_or_float(
                instrument_settings[note.instrument].detune
                if note.instrument in instrument_settings
                else 0
            ),
        }
        if first:
            first = False
            note_info["sorted"] = 1
        yield note_info

# - "Public" API

async def get_note_infos_stream(url):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        text = response.text
    def _get_note_infos():
        data = _extract_data(text)
        note_infos = _get_notes(data)
        return note_infos
    return await asyncio.to_thread(_get_note_infos)

async def get_note_infos(url):
    infos = await get_note_infos_stream(url)
    return await asyncio.to_thread(lambda: list(infos))

# - Command line

parser = argparse.ArgumentParser(
    description="Gets all notes from an Online Sequencer song.",
)
parser.add_argument(
    "url",
    help="link to the song to extract note infos from",
)

if __name__ == "__main__":
    args = parser.parse_args()
    note_infos = asyncio.run(get_note_infos_stream(args.url))
    sys.stdout.write("[")
    first = True
    for note_info in note_infos:
        if first:
            first = False
        else:
            sys.stdout.write(",")
        json.dump(note_info, sys.stdout, separators=(",", ":"))
    sys.stdout.write("]")
