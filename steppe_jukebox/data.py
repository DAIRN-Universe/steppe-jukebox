"""Load the shared route and ordered seasonal classes without guessing or sorting."""

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


SEASONS = (("spring", "Весна"), ("summer", "Лето"))


class DataError(ValueError):
    """The input does not satisfy the route/season CSV contract."""

    def __init__(self, message: str, code: str = "invalid_data", **context):
        super().__init__(message)
        self.code = code
        self.context = context


@dataclass(frozen=True)
class Cell:
    cell_id: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Season:
    key: str
    name: str
    classes: tuple[int | None, ...]
    date: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class Dataset:
    route: tuple[Cell, ...]
    seasons: tuple[Season, ...]
    is_test: bool
    description: str
    description_i18n: tuple[tuple[str, str], ...] = ()


def _rows(path: Path, columns: tuple[str, ...]) -> list[list[str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.reader(source)
            if next(reader, None) != list(columns):
                raise DataError(f"{path.name}: ожидается заголовок {','.join(columns)}", "headers", file=path.name, columns=','.join(columns))
            result = []
            seen = set()
            for row_number, row in enumerate(reader, 2):
                if len(row) != len(columns):
                    raise DataError(f"{path.name}:{row_number}: неверное число столбцов", "columns", file=path.name, row=row_number)
                row = [value.strip() for value in row]
                if not row[0] or row[0] in seen:
                    raise DataError(f"{path.name}:{row_number}: пустой или повторный cell_id", "cell_id", file=path.name, row=row_number)
                seen.add(row[0])
                result.append(row)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DataError(f"Не удалось прочитать {path.name}: {exc}", "read_file", file=path.name) from exc
    if not result:
        raise DataError(f"{path.name}: нет ячеек", "empty", file=path.name)
    return result


def load_route(path: Path) -> tuple[Cell, ...]:
    route = []
    for cell_id, lat_text, lon_text in _rows(Path(path), ("cell_id", "lat", "lon")):
        try:
            lat, lon = float(lat_text), float(lon_text)
        except ValueError as exc:
            raise DataError(f"{path.name}: {cell_id}: координаты должны быть числами", "coordinates", file=path.name, cell=cell_id) from exc
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise DataError(f"{path.name}: {cell_id}: координаты вне допустимых границ", "coordinate_range", file=path.name, cell=cell_id)
        route.append(Cell(cell_id, lat, lon))
    return tuple(route)


def load_classes(path: Path, route: tuple[Cell, ...]) -> tuple[int | None, ...]:
    rows = _rows(Path(path), ("cell_id", "ndvi_class"))
    if [row[0] for row in rows] != [cell.cell_id for cell in route]:
        raise DataError(f"{path.name}: ID и порядок ячеек должны точно совпадать с route.csv", "alignment", file=path.name)
    classes = []
    for cell_id, value in rows:
        if value and value not in {"1", "2", "3", "4", "5"}:
            raise DataError(f"{path.name}: {cell_id}: ndvi_class — целое 1–5 или пустое значение", "ndvi_class", file=path.name, cell=cell_id)
        classes.append(int(value) if value else None)
    return tuple(classes)


def load_dataset(directory: Path) -> Dataset:
    """Only CSV content and optional metadata change when real data arrive.

    Missing metadata defaults to test mode: unverified data must not look like
    attributed satellite observations. No dates or NDVI thresholds are inferred.
    """
    directory = Path(directory)
    route = load_route(directory / "route.csv")
    metadata_path = directory / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise DataError(f"metadata.json: {exc}", "read_file", file="metadata.json") from exc
    if not isinstance(metadata, dict) or type(metadata.get("is_test", True)) is not bool:
        raise DataError("metadata.json: is_test должен быть true или false", "boolean", field="is_test")
    if not isinstance(metadata.get("description", ""), str):
        raise DataError("metadata.json: description должен быть строкой", "string", field="description")
    descriptions = metadata.get("description_i18n", {})
    if not isinstance(descriptions, dict) or any(not isinstance(value, str) for value in descriptions.values()):
        raise DataError("metadata.json: description_i18n должен содержать строки переводов", "translations")
    seasonal_metadata = metadata.get("seasons", {})
    if not isinstance(seasonal_metadata, dict):
        raise DataError("metadata.json: seasons должен быть объектом", "object", field="seasons")
    seasons = []
    for key, name in SEASONS:
        info = seasonal_metadata.get(key, {})
        if not isinstance(info, dict):
            raise DataError(f"metadata.json: seasons.{key} должен быть объектом", "object", field=f"seasons.{key}")
        date, source_url = info.get("date"), info.get("source_url")
        if date is not None and not isinstance(date, str):
            raise DataError(f"metadata.json: {key}.date должен быть строкой", "string", field=f"{key}.date")
        if source_url is not None:
            try:
                url = urlsplit(source_url) if isinstance(source_url, str) else None
                valid_url = url and url.scheme in {"https", "http"} and bool(url.netloc)
            except ValueError:
                valid_url = False
            if not valid_url:
                raise DataError(f"metadata.json: {key}.source_url должен быть HTTP(S) ссылкой", "url", field=f"{key}.source_url")
        seasons.append(Season(key, name, load_classes(directory / f"{key}.csv", route), date, source_url))
    return Dataset(route, tuple(seasons), metadata.get("is_test", True), metadata.get("description", ""), tuple(sorted(descriptions.items())))
