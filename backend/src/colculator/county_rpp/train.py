"""Train and validate the FR3 ElasticNet county RPP estimator."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from sklearn.compose import TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNetCV
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from colculator.county_features.build import FEATURE_FIELDS


SOURCE = "modeled"
CONFIDENCE_LEVEL = 0.95
RANDOM_STATE = 1729
CV_FOLDS = 5
MODEL_FEATURES = FEATURE_FIELDS
TARGETS = {
    "all_items": "rpp_all_items",
    "housing": "rpp_housing",
}


@dataclass(frozen=True)
class TrainConfig:
    year: int
    regions_json: Path
    rpp_json: Path
    features_json: Path
    output_json: Path
    metrics_json: Path
    seed_sql: Path | None = None
    commerce_csv: Path | None = None


def _pipeline() -> TransformedTargetRegressor:
    feature_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            (
                "model",
                ElasticNetCV(
                    l1_ratio=(0.1, 0.5, 0.9),
                    alphas=100,
                    cv=CV_FOLDS,
                    max_iter=50_000,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )
    return TransformedTargetRegressor(
        regressor=feature_pipeline,
        transformer=StandardScaler(),
    )


def _numeric(value: object) -> float:
    if value is None or str(value).strip() == "":
        return np.nan
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"Non-finite model input: {value!r}")
    return result


def _weighted_feature(
    members: Iterable[dict[str, object]], field: str
) -> float:
    numerator = 0.0
    denominator = 0.0
    for member in members:
        value = _numeric(member.get(field))
        weight = _numeric(member.get("population_weight"))
        if np.isnan(value) or np.isnan(weight) or weight <= 0:
            continue
        numerator += value * weight
        denominator += weight
    return np.nan if denominator == 0 else numerator / denominator


def training_matrix(
    regions: list[dict[str, object]],
    feature_records: list[dict[str, object]],
    rpp_records: list[dict[str, object]],
) -> tuple[np.ndarray, dict[str, np.ndarray], list[str]]:
    """Aggregate county inputs to the official state/metro label geographies."""

    county_features = {
        str(record["county_fips"]): record for record in feature_records
    }
    counties = [region for region in regions if region.get("type") == "county"]
    members_by_region: dict[str, list[dict[str, object]]] = {}
    for county in counties:
        feature = county_features.get(str(county["fips"]))
        if feature is None:
            continue
        members_by_region.setdefault(str(county["parent_region_id"]), []).append(feature)
        if county.get("msa_id"):
            members_by_region.setdefault(str(county["msa_id"]), []).append(feature)

    rows: list[list[float]] = []
    targets = {name: [] for name in TARGETS}
    label_regions: list[str] = []
    for record in sorted(rpp_records, key=lambda row: str(row["region_id"])):
        region_id = str(record["region_id"])
        members = members_by_region.get(region_id, [])
        if not members or any(record.get(field) is None for field in TARGETS.values()):
            continue
        rows.append([_weighted_feature(members, field) for field in MODEL_FEATURES])
        for name, field in TARGETS.items():
            targets[name].append(_numeric(record[field]))
        label_regions.append(region_id)
    if len(rows) < CV_FOLDS:
        raise ValueError("Not enough official state/metro labels for cross-validation")
    return (
        np.asarray(rows, dtype=float),
        {name: np.asarray(values, dtype=float) for name, values in targets.items()},
        label_regions,
    )


def _interval(point: float, radius: float) -> dict[str, float]:
    return {
        "lower": round(max(np.finfo(float).eps, point - radius), 3),
        "upper": round(point + radius, 3),
    }


def predict_nonmetro(
    regions: list[dict[str, object]],
    feature_records: list[dict[str, object]],
    models: dict[str, TransformedTargetRegressor],
    radii: dict[str, float],
    *,
    year: int,
    model_version: str,
) -> list[dict[str, object]]:
    """Call estimators only for counties with no official metro coverage."""

    regions_by_fips = {
        str(region["fips"]): region
        for region in regions
        if region.get("type") == "county"
    }
    candidates: list[dict[str, object]] = []
    for feature in feature_records:
        region = regions_by_fips.get(str(feature["county_fips"]))
        if region is None:
            raise ValueError(f"Unknown county feature row {feature['county_fips']}")
        if region.get("msa_id") is not None:
            continue
        candidates.append(feature)

    if not candidates:
        return []
    matrix = np.asarray(
        [[_numeric(record.get(field)) for field in MODEL_FEATURES] for record in candidates],
        dtype=float,
    )
    predictions = {name: model.predict(matrix) for name, model in models.items()}
    records: list[dict[str, object]] = []
    for index, feature in enumerate(candidates):
        all_items = float(predictions["all_items"][index])
        housing = float(predictions["housing"][index])
        if not (
            np.isfinite(all_items)
            and np.isfinite(housing)
            and all_items > 0
            and housing > 0
        ):
            raise ValueError(
                f"Non-positive or non-finite prediction for {feature['county_fips']}"
            )
        records.append(
            {
                "county_fips": str(feature["county_fips"]),
                "year": year,
                "predicted_rpp_all_items": round(all_items, 3),
                "predicted_rpp_housing": round(housing, 3),
                "confidence_interval": {
                    "level": CONFIDENCE_LEVEL,
                    "method": "cross_validated_absolute_residual",
                    "all_items": _interval(all_items, radii["all_items"]),
                    "housing": _interval(housing, radii["housing"]),
                },
                "model_version": model_version,
                "source": SOURCE,
            }
        )
    return records


def _commerce_comparison(
    path: Path | None, estimates: list[dict[str, object]]
) -> dict[str, object]:
    label = "research_estimate_not_verified_truth"
    if path is None:
        return {"status": "not_supplied", "reference_kind": label, "overlap": 0}
    if not path.exists():
        raise ValueError(
            f"Commerce experimental comparison file is required at {path}"
        )
    research: dict[str, float] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"county_fips", "rpp_all_items"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Commerce CSV must contain {sorted(required)}")
        for row in reader:
            research[row["county_fips"].strip().zfill(5)] = _numeric(
                row["rpp_all_items"]
            )
    pairs = [
        (float(row["predicted_rpp_all_items"]), research[str(row["county_fips"])])
        for row in estimates
        if str(row["county_fips"]) in research
    ]
    if not pairs:
        return {"status": "no_overlap", "reference_kind": label, "overlap": 0}
    predicted, reference = (np.asarray(values) for values in zip(*pairs))
    return {
        "status": "computed",
        "reference_kind": label,
        "overlap": len(pairs),
        "rmse": round(float(mean_squared_error(reference, predicted) ** 0.5), 6),
        "mean_absolute_difference": round(float(np.mean(np.abs(reference - predicted))), 6),
    }


def _write_json(path: Path, payload: object, *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(
            payload,
            stream,
            ensure_ascii=False,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        )
        if not compact:
            stream.write("\n")


def _sql(value: object) -> str:
    if isinstance(value, dict):
        value = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _write_seed(path: Path, records: list[dict[str, object]]) -> None:
    columns = (
        "county_fips",
        "year",
        "predicted_rpp_all_items",
        "predicted_rpp_housing",
        "confidence_interval",
        "model_version",
        "source",
    )
    rows = [
        "(" + ",".join(_sql(record[column]) for column in columns) + ")"
        for record in records
    ]
    updates = ",\n  ".join(
        f"{column} = excluded.{column}"
        for column in columns
        if column not in {"county_fips", "year"}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "-- Generated by `npm run train:county-rpp`; do not edit by hand.\n"
        "begin;\n\n"
        "delete from public.county_rpp_estimates as estimate\n"
        "using public.regions as region\n"
        "where region.type = 'county'\n"
        "  and region.fips = estimate.county_fips\n"
        "  and region.msa_id is not null;\n\n"
        f"insert into public.county_rpp_estimates ({', '.join(columns)})\nvalues\n  "
        + ",\n  ".join(rows)
        + "\non conflict (county_fips, year) do update set\n  "
        + updates
        + ";\n\ncommit;\n",
        encoding="utf-8",
    )


def train_county_rpp(config: TrainConfig) -> dict[str, object]:
    regions_payload = json.loads(config.regions_json.read_text(encoding="utf-8"))
    features_payload = json.loads(config.features_json.read_text(encoding="utf-8"))
    rpp_payload = json.loads(config.rpp_json.read_text(encoding="utf-8"))
    if int(features_payload["year"]) != config.year or int(rpp_payload["year"]) != config.year:
        raise ValueError("Features, labels, and requested model year must match")
    regions = regions_payload["regions"]
    features = features_payload["records"]
    rpp = rpp_payload["records"]
    matrix, targets, label_regions = training_matrix(regions, features, rpp)
    folds = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    models: dict[str, TransformedTargetRegressor] = {}
    radii: dict[str, float] = {}
    validation: dict[str, dict[str, float]] = {}
    for name, target in targets.items():
        estimator = _pipeline()
        out_of_fold = cross_val_predict(estimator, matrix, target, cv=folds)
        residuals = np.abs(target - out_of_fold)
        rmse = float(mean_squared_error(target, out_of_fold) ** 0.5)
        radii[name] = float(
            np.quantile(residuals, CONFIDENCE_LEVEL, method="higher")
        )
        validation[name] = {
            "cv_rmse": round(rmse, 6),
            "interval_absolute_residual_quantile": round(radii[name], 6),
        }
        estimator.fit(matrix, target)
        models[name] = estimator

    version_payload = json.dumps(
        {
            "year": config.year,
            "features": MODEL_FEATURES,
            "labels": label_regions,
            "validation": validation,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    model_version = f"elasticnet-{config.year}-{hashlib.sha256(version_payload).hexdigest()[:12]}"
    estimates = predict_nonmetro(
        regions,
        features,
        models,
        radii,
        year=config.year,
        model_version=model_version,
    )
    commerce = _commerce_comparison(config.commerce_csv, estimates)
    metrics = {
        "schema_version": 1,
        "model_version": model_version,
        "year": config.year,
        "selected_model": "ElasticNetCV",
        "selection_reason": (
            "ElasticNet is the required baseline; no more complex model was selected."
        ),
        "feature_names": list(MODEL_FEATURES),
        "explicitly_excluded_features": ["local_wage", "salary", "median_wage"],
        "training_labels": {
            "source": "official_bea",
            "geographies": "state_and_metro",
            "count": len(label_regions),
        },
        "cross_validation": {
            "method": "KFold",
            "folds": CV_FOLDS,
            "shuffle": True,
            "random_state": RANDOM_STATE,
            "targets": validation,
        },
        "confidence_interval": {
            "level": CONFIDENCE_LEVEL,
            "method": "cross_validated_absolute_residual",
        },
        "commerce_experimental_comparison": commerce,
        "prediction_scope": {
            "county_type": "nonmetropolitan_only",
            "count": len(estimates),
        },
    }
    _write_json(
        config.output_json,
        {
            "schema_version": 1,
            "year": config.year,
            "source": SOURCE,
            "model_version": model_version,
            "records": estimates,
        },
        compact=True,
    )
    _write_json(config.metrics_json, metrics, compact=False)
    if config.seed_sql is not None:
        _write_seed(config.seed_sql, estimates)
    return metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument(
        "--commerce-csv",
        type=Path,
        default=Path("data/reference/commerce_experimental_county_rpp.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = TrainConfig(
        year=args.year,
        regions_json=Path("frontend/public/data/regions.json"),
        rpp_json=Path("frontend/public/data/rpp.json"),
        features_json=Path("frontend/public/data/county_features.json"),
        output_json=Path("frontend/public/data/county_rpp_estimates.json"),
        metrics_json=Path("frontend/public/data/county_rpp_model.metrics.json"),
        seed_sql=Path("supabase/seeds/county_rpp_estimates.sql"),
        commerce_csv=args.commerce_csv,
    )
    print(json.dumps(train_county_rpp(config), sort_keys=True))


if __name__ == "__main__":
    main()
