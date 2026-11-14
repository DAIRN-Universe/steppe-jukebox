"""Deterministic mono PCM audio and a timeline from the same sample boundaries."""

import io
import math
import sys
import wave
from array import array
from dataclasses import dataclass

from .data import Cell


BPM = 120
SAMPLE_RATE = 44_100
STEP_SAMPLES = SAMPLE_RATE * 60 // BPM  # One beat per cell, including missing data.
STEP_SECONDS = STEP_SAMPLES / SAMPLE_RATE


@dataclass(frozen=True)
class Note:
    name: str
    label: str
    midi: int
    color: str

    @property
    def frequency(self) -> float:
        return 440 * 2 ** ((self.midi - 69) / 12)


# C major pentatonic. This mapping is shared by every season; never rescale it.
SCALE = (
    Note("C4", "До", 60, "#9c4f22"),
    Note("D4", "Ре", 62, "#ad751e"),
    Note("E4", "Ми", 64, "#788524"),
    Note("G4", "Соль", 67, "#438044"),
    Note("A4", "Ля", 69, "#17634c"),
)
MISSING_COLOR = "#718096"


@dataclass(frozen=True)
class Interval:
    cell_id: str
    ndvi_class: int | None
    note: str | None
    start_sample: int
    end_sample: int

    @property
    def start_s(self) -> float:
        return self.start_sample / SAMPLE_RATE

    @property
    def end_s(self) -> float:
        return self.end_sample / SAMPLE_RATE


@dataclass(frozen=True)
class Track:
    wav: bytes
    intervals: tuple[Interval, ...]

    @property
    def duration_s(self) -> float:
        return self.intervals[-1].end_s


def _tone(note: Note | None) -> bytes:
    samples = array("h", [0]) * STEP_SAMPLES
    if note is not None:
        fade = round(SAMPLE_RATE * 0.01)  # 10 ms avoids clicks without changing the slot.
        for index in range(STEP_SAMPLES):
            envelope = min(1.0, index / fade, (STEP_SAMPLES - 1 - index) / fade)
            samples[index] = round(0.25 * 32767 * envelope * math.sin(2 * math.pi * note.frequency * index / SAMPLE_RATE))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def build_track(route: tuple[Cell, ...], classes: tuple[int | None, ...]) -> Track:
    if not route or len(route) != len(classes):
        raise ValueError("Нужны непустой маршрут и один класс на каждую ячейку")
    if any(value is not None and (type(value) is not int or not 1 <= value <= 5) for value in classes):
        raise ValueError("Классы должны быть целыми 1–5 или None")
    tones = {value: _tone(SCALE[value - 1] if value else None) for value in set(classes)}
    intervals = tuple(
        Interval(cell.cell_id, value, SCALE[value - 1].name if value else None,
                 index * STEP_SAMPLES, (index + 1) * STEP_SAMPLES)
        for index, (cell, value) in enumerate(zip(route, classes, strict=True))
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(b"".join(tones[value] for value in classes))
    return Track(output.getvalue(), intervals)
