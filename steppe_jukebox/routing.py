"""Session-only routes over the existing interior grid; water does not restrict passage."""
from __future__ import annotations

from collections import deque
from dataclasses import replace

from .data import Cell

MAX_WAYPOINTS = 5
MAX_STEPS = 4096


class RouteError(ValueError):
    def __init__(self, code, key=None):
        self.code, self.key = code, key
        super().__init__(code)


def build_path(cells, waypoints):
    lookup = {c['key']: c for c in cells}
    if not isinstance(waypoints, list) or not 1 <= len(waypoints) <= MAX_WAYPOINTS:
        raise RouteError('points_limit')
    for key in waypoints:
        if not isinstance(key, str) or key not in lookup:
            raise RouteError('outside', key if isinstance(key, str) else None)
    interior = {(c['row'], c['col']): c['key'] for c in cells}
    def segment(start, end):
        origin = (lookup[start]['row'], lookup[start]['col'])
        target = (lookup[end]['row'], lookup[end]['col'])
        pending, parents = deque([origin]), {origin: None}
        while pending:
            here = pending.popleft()
            if here == target:
                path = []
                while here is not None:
                    path.append(interior[here]); here = parents[here]
                return path[::-1]
            r, c = here
            for dr, dc in ((-1,0),(0,-1),(0,1),(1,0),(-1,-1),(-1,1),(1,-1),(1,1)):
                neighbor = (r+dr, c+dc)
                if neighbor not in interior or neighbor in parents:
                    continue
                if dr and dc and ((r+dr,c) not in interior or (r,c+dc) not in interior):
                    continue
                parents[neighbor] = here; pending.append(neighbor)
        raise RouteError('no_path')
    path = [waypoints[0]]
    for start, end in zip(waypoints, waypoints[1:]):
        path.extend(segment(start, end)[1:])  # Only the shared segment joint is removed.
        if len(path) > MAX_STEPS:
            raise RouteError('too_long')
    return path


def route_region(region, cells, path):
    lookup = {c['key']: c for c in cells}
    route = []
    for index, key in enumerate(path, 1):
        w, s, e, n = lookup[key]['bounds']
        route.append(Cell(f'USR-{index:04d}', (s+n)/2, (w+e)/2))
    return replace(region, route=tuple(route), landmarks={})


def route_definition(region, cells, path):
    # Rendering keeps the complete region grid. Step identity and cell identity
    # are intentionally separate, including when returning to the same cell.
    first = {}
    for i, key in enumerate(path):
        first.setdefault(key, i)
    return {'route': [vars(c) for c in region.route],
            'map_config': {'bounds': region.grid.bounds, 'cells': cells,
                           'point_ids': [c.cell_id for c in region.route], 'point_keys': path,
                           'route_cells': [{'key': key, 'first_step': i} for key, i in first.items()],
                           'hidden_route_points': []},
            'intervals': region.intervals([''] * len(path))}
