"""Export the exact tracks and timing tables used by the player."""

import argparse
import csv
from pathlib import Path

from .data import load_dataset
from .sound import build_track


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    dataset = load_dataset(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for season in dataset.seasons:
        track = build_track(dataset.route, season.classes)
        (args.output_dir / f"{season.key}.wav").write_bytes(track.wav)
        with (args.output_dir / f"{season.key}_timing.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(("cell_id", "ndvi_class", "note", "start_sample", "end_sample", "start_s", "end_s"))
            for slot in track.intervals:
                writer.writerow((slot.cell_id, slot.ndvi_class, slot.note, slot.start_sample,
                                 slot.end_sample, slot.start_s, slot.end_s))
        print(f"{season.name}: {len(track.intervals)} ячеек, {track.duration_s:g} с → {args.output_dir / season.key}")
    if dataset.journey is not None:
        journey = dataset.journey
        track = build_track(dataset.route, tuple(step.ndvi_class for step in journey.steps))
        (args.output_dir / "journey.wav").write_bytes(track.wav)
        with (args.output_dir / "journey_timing.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(("cell_id", "date", "ndvi_class", "note", "start_sample", "end_sample", "start_s", "end_s"))
            for step, slot in zip(journey.steps, track.intervals, strict=True):
                writer.writerow((slot.cell_id, step.date, slot.ndvi_class, slot.note, slot.start_sample,
                                 slot.end_sample, slot.start_s, slot.end_s))
        print(f"Journey: {len(track.intervals)} steps, {track.duration_s:g} s → {args.output_dir / 'journey'}")


if __name__ == "__main__":
    main()
