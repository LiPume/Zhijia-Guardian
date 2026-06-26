from __future__ import annotations

from collections import defaultdict
from html import escape

from zhijia_guardian.experiments.eval_metrics import EvalRow
from zhijia_guardian.schemas.diagnosis import DiagnosisRecord
from zhijia_guardian.schemas.scenario import FrameRecord, ScenarioRecord


def render_bev_svg(scenario: ScenarioRecord, diagnosis: DiagnosisRecord, width: int = 920, height: int = 520) -> str:
    paths = _collect_bev_paths(scenario, diagnosis)
    bounds = _bounds([point for points in paths.values() for point in points])
    margin = 42

    def project(point: tuple[float, float]) -> tuple[float, float]:
        min_x, max_x, min_y, max_y = bounds
        x_range = max(max_x - min_x, 1.0)
        y_range = max(max_y - min_y, 1.0)
        x = margin + (point[0] - min_x) / x_range * (width - margin * 2)
        y = height - margin - (point[1] - min_y) / y_range * (height - margin * 2)
        return x, y

    parts = _svg_header(width, height)
    parts.append(_style())
    parts.append(f'<text x="24" y="30" class="title">BEV {escape(scenario.scenario_id)}</text>')
    parts.append(
        f'<text x="24" y="52" class="muted">pred={escape(str(diagnosis.predicted_fault_type))} '
        f'root={escape(str(diagnosis.predicted_root_module))}</text>'
    )
    parts.append(_legend(24, 78, [("ego", "#1f77b4"), ("actor", "#d62728"), ("plan", "#2ca02c"), ("detection", "#9467bd")]))

    for name, color, dash in [
        ("ego", "#1f77b4", ""),
        ("actors", "#d62728", ""),
        ("planning", "#2ca02c", " stroke-dasharray=\"7 5\""),
        ("detections", "#9467bd", " stroke-dasharray=\"3 5\""),
    ]:
        points = paths.get(name, [])
        if len(points) >= 2:
            projected = " ".join(f"{x:.1f},{y:.1f}" for x, y in [project(point) for point in points])
            parts.append(f'<polyline points="{projected}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        for point in points:
            x, y = project(point)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.8" fill="{color}" opacity="0.78"/>')

    start = paths.get("ego", [])[:1]
    end = paths.get("ego", [])[-1:]
    if start:
        x, y = project(start[0])
        parts.append(f'<text x="{x + 8:.1f}" y="{y - 8:.1f}" class="label">start</text>')
    if end:
        x, y = project(end[0])
        parts.append(f'<text x="{x + 8:.1f}" y="{y - 8:.1f}" class="label">end</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_timeline_svg(scenario: ScenarioRecord, diagnosis: DiagnosisRecord, width: int = 920) -> str:
    items = []
    for event in scenario.events_observed:
        items.append((event.timestamp, "event", event.event_type, event.description, "context"))
    for evidence in diagnosis.evidence:
        if evidence.time is None:
            continue
        items.append((evidence.time, "evidence", evidence.metric_name, evidence.description, evidence.status))
    items.sort(key=lambda item: (item[0], item[1], item[2]))
    height = max(180, 92 + len(items) * 34)
    margin = 42
    max_t = max([frame.timestamp for frame in scenario.frames] + [item[0] for item in items] + [1.0])
    min_t = min([frame.timestamp for frame in scenario.frames] + [item[0] for item in items] + [0.0])
    span = max(max_t - min_t, 1.0)

    def x_at(timestamp: float) -> float:
        return margin + (timestamp - min_t) / span * (width - margin * 2)

    colors = {
        "violation": "#d62728",
        "normal": "#2ca02c",
        "uncertain": "#7f7f7f",
        "context": "#ffbf00",
    }
    parts = _svg_header(width, height)
    parts.append(_style())
    parts.append(f'<text x="24" y="30" class="title">Evidence Timeline {escape(scenario.scenario_id)}</text>')
    axis_y = 74
    parts.append(f'<line x1="{margin}" y1="{axis_y}" x2="{width - margin}" y2="{axis_y}" stroke="#222" stroke-width="1.5"/>')
    for timestamp in _ticks(min_t, max_t):
        x = x_at(timestamp)
        parts.append(f'<line x1="{x:.1f}" y1="{axis_y - 5}" x2="{x:.1f}" y2="{axis_y + 5}" stroke="#222"/>')
        parts.append(f'<text x="{x - 10:.1f}" y="{axis_y + 24}" class="tick">{timestamp:.1f}s</text>')

    for index, (timestamp, kind, name, description, status) in enumerate(items):
        y = 118 + index * 34
        x = x_at(timestamp)
        color = colors.get(status, "#7f7f7f")
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}"/>')
        parts.append(f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{y:.1f}" stroke="{color}" opacity="0.35"/>')
        label = f"{timestamp:.2f}s {kind}:{name}"
        parts.append(f'<text x="{margin}" y="{y + 4:.1f}" class="label">{escape(label)}</text>')
        parts.append(f'<text x="{margin + 230}" y="{y + 4:.1f}" class="muted">{escape(description[:88])}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_confusion_matrix_svg(rows: list[EvalRow], width: int = 860) -> str:
    labels = sorted(set([row.true_fault_type for row in rows] + [row.pred_fault_type for row in rows]))
    counts = defaultdict(int)
    for row in rows:
        counts[(row.true_fault_type, row.pred_fault_type)] += 1
    cell = 70
    left = 210
    top = 92
    height = top + cell * len(labels) + 80
    max_count = max(counts.values()) if counts else 1
    parts = _svg_header(width, height)
    parts.append(_style())
    parts.append('<text x="24" y="30" class="title">Confusion Matrix</text>')
    parts.append('<text x="24" y="54" class="muted">rows=true fault type, columns=predicted fault type</text>')
    for col, label in enumerate(labels):
        x = left + col * cell + cell / 2
        parts.append(
            f'<text transform="translate({x:.1f},{top - 14}) rotate(-38)" text-anchor="start" class="tick">{escape(label)}</text>'
        )
    for row_index, true_label in enumerate(labels):
        y = top + row_index * cell
        parts.append(f'<text x="{left - 12}" y="{y + cell / 2 + 5:.1f}" text-anchor="end" class="tick">{escape(true_label)}</text>')
        for col, pred_label in enumerate(labels):
            x = left + col * cell
            count = counts[(true_label, pred_label)]
            intensity = count / max_count
            fill = _blend("#f7fbff", "#08519c", intensity)
            parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{fill}" stroke="#fff" stroke-width="2"/>')
            if count:
                text_color = "#fff" if intensity > 0.55 else "#111"
                parts.append(
                    f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 5:.1f}" text-anchor="middle" '
                    f'fill="{text_color}" class="count">{count}</text>'
                )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _collect_bev_paths(scenario: ScenarioRecord, diagnosis: DiagnosisRecord) -> dict[str, list[tuple[float, float]]]:
    paths: dict[str, list[tuple[float, float]]] = {
        "ego": [(frame.ego.x, frame.ego.y) for frame in scenario.frames],
        "actors": [],
        "planning": [],
        "detections": [],
    }
    actor_tracks: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for frame in scenario.frames:
        for actor in frame.actors_gt:
            actor_tracks[actor.actor_id].append((actor.x, actor.y))
    for track in actor_tracks.values():
        paths["actors"].extend(track)

    frame = _select_frame(scenario, diagnosis)
    if frame is not None:
        paths["planning"] = [(point.x, point.y) for point in frame.planning.trajectory]
        paths["detections"] = [(det.x, det.y) for det in frame.perception.detections]
    return paths


def _select_frame(scenario: ScenarioRecord, diagnosis: DiagnosisRecord) -> FrameRecord | None:
    if not scenario.frames:
        return None
    target = diagnosis.predicted_fault_start_time
    candidates = [frame for frame in scenario.frames if frame.planning.available or frame.perception.available]
    if not candidates:
        candidates = scenario.frames
    if target is None:
        return candidates[len(candidates) // 2]
    return min(candidates, key=lambda frame: abs(frame.timestamp - target))


def _bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    if not points:
        return -1.0, 1.0, -1.0, 1.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad_x = max((max_x - min_x) * 0.12, 5.0)
    pad_y = max((max_y - min_y) * 0.20, 4.0)
    return min_x - pad_x, max_x + pad_x, min_y - pad_y, max_y + pad_y


def _ticks(min_t: float, max_t: float) -> list[float]:
    span = max(max_t - min_t, 1.0)
    step = 1.0 if span <= 8 else 2.0
    start = int(min_t // step) * step
    ticks = []
    current = start
    while current <= max_t + 0.001:
        if current >= min_t - 0.001:
            ticks.append(current)
        current += step
    return ticks


def _svg_header(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        '<rect width="100%" height="100%" fill="#fbfbf8"/>',
    ]


def _style() -> str:
    return (
        "<style>"
        ".title{font:700 18px Arial, sans-serif;fill:#111}"
        ".label{font:12px Arial, sans-serif;fill:#111}"
        ".muted{font:12px Arial, sans-serif;fill:#555}"
        ".tick{font:11px Arial, sans-serif;fill:#333}"
        ".count{font:700 16px Arial, sans-serif}"
        "</style>"
    )


def _legend(x: int, y: int, items: list[tuple[str, str]]) -> str:
    parts = []
    cursor = x
    for label, color in items:
        parts.append(f'<rect x="{cursor}" y="{y}" width="12" height="12" fill="{color}"/>')
        parts.append(f'<text x="{cursor + 18}" y="{y + 11}" class="tick">{escape(label)}</text>')
        cursor += 92
    return "".join(parts)


def _blend(light_hex: str, dark_hex: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    light = _hex_to_rgb(light_hex)
    dark = _hex_to_rgb(dark_hex)
    rgb = tuple(round(light[i] + (dark[i] - light[i]) * t) for i in range(3))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
