#!/usr/bin/env python3
"""Import Apple Health export.zip into fitness corpus (stream XML, no full extract)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import iterparse

from medbots.corpus_io import load_patient_dob, resolve_corpus
from medbots.zip_safety import UnsafeZipError, validate_zip_archive

VALID_DATE_MIN = "2015-01-01"

RECORD_TYPES = {
    "HKQuantityTypeIdentifierBodyMass": "weight_kg",
    "HKQuantityTypeIdentifierBodyFatPercentage": "body_fat_pct",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierRestingHeartRate": "hr_resting_bpm",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn_ms",
    "HKQuantityTypeIdentifierVO2Max": "vo2max_ml_kg_min",
}

SLEEP_ASLEEP = {
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
}

WORKOUT_TYPE_RU: dict[str, str] = {
    "HKWorkoutActivityTypeRunning": "Бег",
    "HKWorkoutActivityTypeWalking": "Ходьба",
    "HKWorkoutActivityTypeCycling": "Велосипед",
    "HKWorkoutActivityTypeSwimming": "Плавание",
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "Силовая",
    "HKWorkoutActivityTypeFunctionalStrengthTraining": "Функциональная силовая",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "HIIT",
    "HKWorkoutActivityTypeYoga": "Йога",
    "HKWorkoutActivityTypeHiking": "Поход",
    "HKWorkoutActivityTypeElliptical": "Эллипс",
    "HKWorkoutActivityTypeRowing": "Гребля",
    "HKWorkoutActivityTypeStairClimbing": "Лестница",
    "HKWorkoutActivityTypeCoreTraining": "Кор",
    "HKWorkoutActivityTypeCrossTraining": "Кросс-тренинг",
    "HKWorkoutActivityTypeMindAndBody": "Mind & Body",
    "HKWorkoutActivityTypeOther": "Другое",
}


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(default)


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_apple_datetime(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    m = re.match(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) ([+-]\d{4})$", s)
    if m:
        tz = m.group(3)
        tz_iso = f"{tz[:3]}:{tz[3:]}"
        return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}{tz_iso}")
    return datetime.fromisoformat(s)


def is_valid_day(day: str | None) -> bool:
    return bool(day) and day >= VALID_DATE_MIN


def track_date(stats: ImportStats, day: str | None) -> None:
    if not is_valid_day(day):
        return
    stats.date_min = day if stats.date_min is None else min(stats.date_min, day)
    stats.date_max = day if stats.date_max is None else max(stats.date_max, day)


def local_date(s: str) -> str:
    return parse_apple_datetime(s).date().isoformat()


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_main_xml(zf: zipfile.ZipFile) -> str:
    candidates = [
        i.filename
        for i in zf.infolist()
        if i.filename.endswith(".xml") and "cda" not in i.filename.lower()
    ]
    if not candidates:
        raise FileNotFoundError("Main HealthKit XML not found in zip")
    return max(candidates, key=lambda n: zf.getinfo(n).file_size)


def find_export_dob(zf: zipfile.ZipFile, xml_name: str) -> str | None:
    with zf.open(xml_name) as fh:
        for _event, elem in iterparse(fh, events=("end",)):
            if elem.tag == "Me":
                dob = elem.get("HKCharacteristicTypeIdentifierDateOfBirth")
                elem.clear()
                if dob:
                    return dob.split(" ")[0]
                return None
            elem.clear()
    return None


@dataclass
class DailyAgg:
    weight_kg: float | None = None
    weight_at: str | None = None
    body_fat_pct: float | None = None
    body_fat_at: str | None = None
    steps: int = 0
    hr_resting_sum: float = 0.0
    hr_resting_n: int = 0
    hrv_sum: float = 0.0
    hrv_n: int = 0
    vo2max: float | None = None
    vo2max_at: str | None = None
    sleep_seconds: float = 0.0
    active_energy_kcal: float | None = None
    exercise_min: float | None = None
    stand_hours: float | None = None
    activity_steps: int | None = None

    def resting_hr_avg(self) -> int | None:
        if self.hr_resting_n == 0:
            return None
        return round(self.hr_resting_sum / self.hr_resting_n)

    def hrv_avg(self) -> float | None:
        if self.hrv_n == 0:
            return None
        return round(self.hrv_sum / self.hrv_n, 1)


@dataclass
class ImportStats:
    records_seen: int = 0
    records_matched: int = 0
    workouts: int = 0
    activity_summaries: int = 0
    sleep_segments: int = 0
    date_min: str | None = None
    date_max: str | None = None
    type_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def normalize_body_fat(value: float, unit: str) -> float:
    if unit == "%" or value > 1.5:
        return round(value, 2)
    return round(value * 100.0, 2)


def sleep_hours_for_date(segments: list[tuple[str, str, str]]) -> dict[str, float]:
    by_wake: dict[str, float] = defaultdict(float)
    for start_s, end_s, value in segments:
        if value not in SLEEP_ASLEEP:
            continue
        start = parse_apple_datetime(start_s)
        end = parse_apple_datetime(end_s)
        secs = max(0.0, (end - start).total_seconds())
        wake_date = end.date().isoformat()
        by_wake[wake_date] += secs
    return by_wake


def match_route_file(workout_start: str, routes: list[str]) -> str | None:
    d = parse_apple_datetime(workout_start)
    day = d.strftime("%Y-%m-%d")
    candidates = [r for r in routes if f"route_{day}_" in r]
    if not candidates:
        return None
    if len(candidates) == 1:
        return Path(candidates[0]).name
    best: str | None = None
    best_delta = 999999.0
    for r in candidates:
        m = re.search(r"route_\d{4}-\d{2}-\d{2}_(\d+\.\d+)(am|pm)", r, re.I)
        if not m:
            continue
        h = float(m.group(1))
        if m.group(2).lower() == "pm" and h < 12:
            h += 12
        if m.group(2).lower() == "am" and h == 12:
            h = 0
        wmins = h * 60 + (h % 1) * 60
        dmins = d.hour * 60 + d.minute
        delta = abs(wmins - dmins)
        if delta < best_delta:
            best_delta = delta
            best = Path(r).name
    return best


def stream_import(zip_path: Path) -> tuple[dict[str, DailyAgg], list[dict], ImportStats, str | None]:
    daily: dict[str, DailyAgg] = defaultdict(DailyAgg)
    sleep_buf: list[tuple[str, str, str]] = []
    workouts: list[dict[str, Any]] = []
    stats = ImportStats()
    export_dob: str | None = None

    with zipfile.ZipFile(zip_path) as zf:
        validate_zip_archive(zf, zip_size=zip_path.stat().st_size)
        xml_name = find_main_xml(zf)
        routes = [
            i.filename
            for i in zf.infolist()
            if "workout-routes/" in i.filename and i.filename.endswith(".gpx")
        ]
        export_dob = find_export_dob(zf, xml_name)

        with zf.open(xml_name) as fh:
            for _event, elem in iterparse(fh, events=("end",)):
                tag = elem.tag
                if tag == "Record":
                    stats.records_seen += 1
                    rtype = elem.get("type") or ""
                    stats.type_counts[rtype] += 1
                    if rtype in RECORD_TYPES:
                        stats.records_matched += 1
                        field_name = RECORD_TYPES[rtype]
                        start = elem.get("startDate") or ""
                        day = local_date(start) if start else None
                        if day and is_valid_day(day):
                            track_date(stats, day)
                            agg = daily[day]
                            try:
                                val = float(elem.get("value") or "0")
                            except ValueError:
                                val = 0.0
                            unit = elem.get("unit") or ""
                            if field_name == "weight_kg":
                                if agg.weight_at is None or start > agg.weight_at:
                                    agg.weight_kg = round(val, 2)
                                    agg.weight_at = start
                            elif field_name == "body_fat_pct":
                                bf = normalize_body_fat(val, unit)
                                if agg.body_fat_at is None or start > agg.body_fat_at:
                                    agg.body_fat_pct = bf
                                    agg.body_fat_at = start
                            elif field_name == "steps":
                                agg.steps += int(round(val))
                            elif field_name == "hr_resting_bpm":
                                agg.hr_resting_sum += val
                                agg.hr_resting_n += 1
                            elif field_name == "hrv_sdnn_ms":
                                agg.hrv_sum += val
                                agg.hrv_n += 1
                            elif field_name == "vo2max_ml_kg_min":
                                if agg.vo2max_at is None or start > agg.vo2max_at:
                                    agg.vo2max = round(val, 2)
                                    agg.vo2max_at = start
                    elif rtype == "HKCategoryTypeIdentifierSleepAnalysis":
                        stats.sleep_segments += 1
                        start = elem.get("startDate") or ""
                        end = elem.get("endDate") or ""
                        value = elem.get("value") or ""
                        if start and end:
                            sleep_buf.append((start, end, value))
                elif tag == "Workout":
                    stats.workouts += 1
                    start = elem.get("startDate") or ""
                    end = elem.get("endDate") or ""
                    wtype = elem.get("workoutActivityType") or "HKWorkoutActivityTypeOther"
                    duration = float(elem.get("duration") or 0)
                    dur_unit = elem.get("durationUnit") or "min"
                    duration_min = duration * 60 if dur_unit == "s" else duration
                    dist = elem.get("totalDistance")
                    dist_unit = elem.get("totalDistanceUnit") or "km"
                    distance_km = None
                    if dist:
                        d = float(dist)
                        distance_km = round(d / 1000, 3) if dist_unit == "m" else round(d, 3)
                    energy = elem.get("totalEnergyBurned")
                    calories = round(float(energy), 1) if energy else None
                    day = local_date(start) if start else date.today().isoformat()
                    if not is_valid_day(day):
                        elem.clear()
                        continue
                    track_date(stats, day)
                    ext = hashlib.sha1(f"{start}|{end}|{wtype}".encode()).hexdigest()[:16]
                    route = match_route_file(start, routes) if start else None
                    workouts.append(
                        {
                            "date": day,
                            "recorded_at": to_utc_iso(parse_apple_datetime(start)) if start else "",
                            "source": "apple_health",
                            "external_id": f"apple_health_workout:{ext}",
                            "workout_type": wtype,
                            "workout_type_ru": WORKOUT_TYPE_RU.get(
                                wtype, wtype.replace("HKWorkoutActivityType", "")
                            ),
                            "start_at": start,
                            "end_at": end,
                            "duration_min": round(duration_min, 1),
                            "distance_km": distance_km,
                            "calories_kcal": calories,
                            "device": elem.get("sourceName"),
                            "has_route_gpx": route is not None,
                            "route_file": route,
                        }
                    )
                elif tag == "ActivitySummary":
                    stats.activity_summaries += 1
                    dc = elem.get("dateComponents") or ""
                    if len(dc) >= 10:
                        day = dc[:10]
                        if not is_valid_day(day):
                            elem.clear()
                            continue
                        track_date(stats, day)
                        agg = daily[day]
                        ae = elem.get("activeEnergyBurned")
                        if ae:
                            agg.active_energy_kcal = round(float(ae), 1)
                        ex = elem.get("appleExerciseTime")
                        if ex:
                            agg.exercise_min = round(float(ex), 1)
                        sh = elem.get("appleStandHours")
                        if sh:
                            agg.stand_hours = round(float(sh), 1)
                        sc = elem.get("stepCount")
                        if sc:
                            agg.activity_steps = int(float(sc))
                elem.clear()

    sleep_by_day = sleep_hours_for_date(sleep_buf)
    for day, secs in sleep_by_day.items():
        if is_valid_day(day):
            daily[day].sleep_seconds = secs

    return daily, workouts, stats, export_dob


def build_body_metrics(daily: dict[str, DailyAgg]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for day in sorted(daily.keys()):
        if not is_valid_day(day):
            continue
        agg = daily[day]
        entry: dict[str, Any] = {
            "date": day,
            "recorded_at": f"{day}T23:59:59Z",
            "source": "apple_health",
            "external_id": f"apple_health_daily:{day}",
        }
        if agg.weight_kg is not None:
            entry["weight_kg"] = agg.weight_kg
        if agg.body_fat_pct is not None:
            entry["body_fat_pct"] = agg.body_fat_pct
        steps = agg.activity_steps if agg.activity_steps is not None else (agg.steps or None)
        if steps:
            entry["steps"] = steps
        if agg.sleep_seconds > 0:
            entry["sleep_hours"] = round(agg.sleep_seconds / 3600.0, 2)
        hr = agg.resting_hr_avg()
        if hr is not None:
            entry["hr_bpm"] = hr
        if agg.hrv_avg() is not None:
            entry["hrv_sdnn_ms"] = agg.hrv_avg()
        if agg.vo2max is not None:
            entry["vo2max_ml_kg_min"] = agg.vo2max
        if agg.active_energy_kcal is not None:
            entry["active_energy_kcal"] = agg.active_energy_kcal
        if agg.exercise_min is not None:
            entry["exercise_min"] = agg.exercise_min
        if agg.stand_hours is not None:
            entry["stand_hours"] = agg.stand_hours
        if len(entry) > 4:
            entries.append(entry)
    return entries


def parse_ecg_from_zip(zip_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as zf:
        validate_zip_archive(zf, zip_size=zip_path.stat().st_size)
        for info in zf.infolist():
            if "electrocardiograms/" not in info.filename or not info.filename.endswith(".csv"):
                continue
            raw = zf.read(info).decode("utf-8", errors="replace")
            lines = raw.splitlines()
            meta: dict[str, str] = {}
            for line in lines[:12]:
                if "," in line and not line.startswith("Отведение"):
                    k, _, v = line.partition(",")
                    meta[k.strip()] = v.strip()
            classification = meta.get("Классификация", meta.get("Classification", ""))
            recorded = meta.get("Дата записи", meta.get("Recorded Date", ""))
            device = meta.get("Устройство", meta.get("Device", ""))
            fname = Path(info.filename).name
            date_part = fname.replace("ecg_", "").replace(".csv", "").split("_")[0]
            records.append(
                {
                    "source": "apple_health",
                    "external_id": f"apple_health_ecg:{fname}",
                    "file": fname,
                    "date": date_part,
                    "recorded_at_local": recorded,
                    "classification": classification,
                    "device": device,
                    "sample_rate_hz": meta.get("Частота замеров", meta.get("Sample Rate", "")),
                }
            )
    records.sort(key=lambda r: r["date"])
    return records


def list_gpx_index(zip_path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as zf:
        validate_zip_archive(zf, zip_size=zip_path.stat().st_size)
        for info in zf.infolist():
            if "workout-routes/" not in info.filename or not info.filename.endswith(".gpx"):
                continue
            name = Path(info.filename).name
            m = re.match(r"route_(\d{4}-\d{2}-\d{2})_", name)
            out.append(
                {
                    "file": name,
                    "date": m.group(1) if m else None,
                    "size_bytes": info.file_size,
                }
            )
    out.sort(key=lambda x: (x["date"] or "", x["file"]))
    return out


def quality_report(
    entries: list[dict],
    workouts: list[dict],
    stats: ImportStats,
    export_dob: str | None,
    patient_dob: str | None,
) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []

    if stats.records_seen < 1000:
        warnings.append(f"Few Record nodes in XML: {stats.records_seen}")
    if stats.workouts < 1:
        warnings.append(f"No workouts found: {stats.workouts}")
    if not entries:
        issues.append("BODY_METRICS entries empty after aggregation")

    weights = [e["weight_kg"] for e in entries if e.get("weight_kg")]
    if weights and (min(weights) < 40 or max(weights) > 200):
        warnings.append(f"Weight outside typical range: {min(weights)}–{max(weights)} kg")

    if export_dob and patient_dob and export_dob != patient_dob:
        warnings.append(f"Export DOB ({export_dob}) != PATIENT_PROFILE ({patient_dob})")

    workouts_with_route = sum(1 for w in workouts if w.get("has_route_gpx"))
    return {
        "status": "fail" if issues else ("warn" if warnings else "ok"),
        "issues": issues,
        "warnings": warnings,
        "checks": {
            "records_seen": stats.records_seen,
            "daily_metric_days": len(entries),
            "workouts": len(workouts),
            "workouts_with_gpx": workouts_with_route,
            "date_range": [stats.date_min, stats.date_max],
            "export_dob": export_dob,
            "patient_dob": patient_dob,
        },
    }


def write_summary_md(meta: dict[str, Any], entries: list[dict], workouts: list[dict], ecg: list[dict]) -> str:
    recent_metrics = entries[-7:]
    recent_workouts = workouts[-10:]
    lines = [
        "# Apple Health — summary",
        "",
        f"**Imported:** {meta.get('imported_at', '')}",
        f"**Range:** {meta.get('date_range', ['', ''])[0]} — {meta.get('date_range', ['', ''])[1]}",
        f"**Days with metrics:** {meta.get('daily_metric_days', 0)}",
        f"**Workouts:** {meta.get('workouts', 0)}",
        f"**ECG records:** {len(ecg)}",
        "",
        "## Quality",
        f"- Status: **{meta.get('quality', {}).get('status', 'unknown')}**",
    ]
    for w in meta.get("quality", {}).get("warnings", []):
        lines.append(f"- WARN: {w}")
    for i in meta.get("quality", {}).get("issues", []):
        lines.append(f"- ERROR: {i}")
    lines.extend(["", "## Last 7 days", ""])
    if recent_metrics:
        lines.append("| date | weight | steps | sleep_h | exercise_min | hr |")
        lines.append("|------|--------|-------|---------|--------------|-----|")
        for e in recent_metrics:
            lines.append(
                f"| {e['date']} | {e.get('weight_kg', '')} | {e.get('steps', '')} | "
                f"{e.get('sleep_hours', '')} | {e.get('exercise_min', '')} | {e.get('hr_bpm', '')} |"
            )
    else:
        lines.append("_no data_")
    lines.extend(["", "## Last 10 workouts", ""])
    for w in recent_workouts:
        lines.append(
            f"- {w['date']} **{w.get('workout_type_ru', w.get('workout_type'))}** "
            f"{w.get('duration_min')} min"
        )
    lines.append("")
    lines.append("Full data: `BODY_METRICS.json`, `WORKOUTS.json`, `ECG_RECORDS.json`, `APPLE_HEALTH_META.json`.")
    return "\n".join(lines)


def merge_entries(existing: list[dict], new_apple: list[dict]) -> list[dict]:
    kept = [e for e in existing if e.get("source") != "apple_health"]
    by_id = {e["external_id"]: e for e in new_apple if e.get("external_id")}
    merged = kept + list(by_id.values())
    merged.sort(key=lambda e: e.get("date") or "")
    return merged


def merge_workouts(existing: list[dict], new_apple: list[dict]) -> list[dict]:
    kept = [s for s in existing if s.get("source") != "apple_health"]
    by_id = {s["external_id"]: s for s in new_apple if s.get("external_id")}
    merged = kept + list(by_id.values())
    merged.sort(key=lambda s: (s.get("date") or "", s.get("start_at") or ""))
    return merged


def run_import(
    bot_root: Path,
    zip_path: Path,
    *,
    corpus: Path | None = None,
    copy_zip: bool = False,
) -> dict[str, Any]:
    root = bot_root.resolve()
    corp = resolve_corpus(corpus) if corpus else resolve_corpus(root / "structured_database")
    fitness = corp / "fitness"
    zip_path = zip_path.resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    if copy_zip:
        dest_dir = root / "sources" / "apple_health"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / zip_path.name
        if not dest.exists() or dest.stat().st_size != zip_path.stat().st_size:
            dest.write_bytes(zip_path.read_bytes())

    daily, workouts, stats, export_dob = stream_import(zip_path)
    entries = build_body_metrics(daily)
    ecg = parse_ecg_from_zip(zip_path)
    gpx_index = list_gpx_index(zip_path)

    profile_path = corp / "PATIENT_PROFILE.json"
    profile = _load_json(profile_path, {})
    patient_dob = profile.get("dob") or load_patient_dob(corp) or None
    quality = quality_report(entries, workouts, stats, export_dob, patient_dob)

    imported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "version": 1,
        "imported_at": imported_at,
        "source_zip": str(zip_path),
        "source_zip_size_mb": round(zip_path.stat().st_size / (1024 * 1024), 1),
        "export_dob": export_dob,
        "date_range": [stats.date_min, stats.date_max],
        "daily_metric_days": len(entries),
        "workouts": len(workouts),
        "ecg_records": len(ecg),
        "gpx_routes": len(gpx_index),
        "records_seen": stats.records_seen,
        "activity_summaries": stats.activity_summaries,
        "top_record_types": dict(sorted(stats.type_counts.items(), key=lambda x: -x[1])[:15]),
        "quality": quality,
        "gpx_index_sample": gpx_index[:5],
        "note": "Aggregated JSON only; export.xml is not stored in corpus.",
    }

    fitness.mkdir(parents=True, exist_ok=True)
    bm = _load_json(fitness / "BODY_METRICS.json", {"version": 1, "entries": [], "meta": {}})
    bm["entries"] = merge_entries(bm.get("entries") or [], entries)
    bm["meta"] = {
        "apple_health_last_import": imported_at,
        "apple_health_days": len(entries),
    }
    _save_json(fitness / "BODY_METRICS.json", bm)

    wo = _load_json(fitness / "WORKOUTS.json", {"version": 1, "plan": [], "sessions": [], "meta": {}})
    wo["sessions"] = merge_workouts(wo.get("sessions") or [], workouts)
    wo["meta"] = {
        "apple_health_last_import": imported_at,
        "apple_health_sessions": len(workouts),
    }
    _save_json(fitness / "WORKOUTS.json", wo)

    _save_json(
        fitness / "ECG_RECORDS.json",
        {"version": 1, "records": ecg, "meta": {"source": "apple_health"}},
    )
    _save_json(fitness / "APPLE_HEALTH_META.json", meta)
    (fitness / "APPLE_HEALTH_SUMMARY.md").write_text(
        write_summary_md(meta, entries, workouts, ecg), encoding="utf-8"
    )

    if export_dob and not patient_dob:
        profile["dob"] = export_dob
        profile["notes"] = (profile.get("notes") or "") + " DOB from Apple Health export."
        _save_json(profile_path, profile)

    return {
        "quality": quality["status"],
        "daily_metric_days": len(entries),
        "workouts": len(workouts),
        "ecg_records": len(ecg),
        "date_range": [stats.date_min, stats.date_max],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Import Apple Health export.zip into fitness/")
    ap.add_argument("--zip", type=Path, required=True, help="Path to Apple Health export.zip")
    ap.add_argument("--bot-root", type=Path, default=Path.cwd())
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--copy-zip", action="store_true", help="Copy zip to sources/apple_health/")
    args = ap.parse_args()
    stats = run_import(args.bot_root, args.zip, corpus=args.corpus, copy_zip=args.copy_zip)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if stats["quality"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
