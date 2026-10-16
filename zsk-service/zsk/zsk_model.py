"""Reusable ZSK-style SYNTHETIC health classifier logic for wrapping in an MCP server.

NOT a validated industrial diagnostic. Input is timestamped 5-minute readings.
Full retraining is used (RandomForest has no incremental partial_fit).
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix

MEASURED = [
    'screw_speed_rpm', 'screw_torque_pct', 'motor_current_a', 'motor_power_kw',
    'gearbox_vibration_rms_mm_s', 'gearbox_oil_temp_c', 'barrel_zone_temp_c',
    'melt_temp_c', 'melt_pressure_bar', 'feed_rate_kg_h',
]
ROLLING = ['screw_torque_pct', 'gearbox_vibration_rms_mm_s',
           'gearbox_oil_temp_c', 'melt_pressure_bar']
FEATURES = MEASURED + ['recipe_B', 'recipe_C'] + [
    f'{name}_{suffix}' for name in ROLLING for suffix in ('mean_3', 'std_3')
]
LABELS = {0: 'Faulty', 1: 'Healthy'}


def load_csv(path: str | Path) -> list[dict]:
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_csv(path: str | Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError('No rows to write')
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def feature_matrix(rows: list[dict]) -> np.ndarray:
    """Past-only 3-point rolling features within each machine, in time order.

    Rows MUST be provided in chronological order per machine. For an individual
    fresh measurement, supply previous two observations before the new reading.
    """
    if not rows:
        raise ValueError('Empty input')
    history = defaultdict(lambda: {k: deque(maxlen=3) for k in ROLLING})
    last_timestamp = {}
    features = []
    for row in rows:
        machine = row.get('machine_id', 'default')
        timestamp = datetime.fromisoformat(str(row['timestamp']))
        if machine in last_timestamp and timestamp <= last_timestamp[machine]:
            raise ValueError(f'Unordered or duplicate timestamp for {machine}')
        last_timestamp[machine] = timestamp
        record = {key: float(row[key]) for key in MEASURED}
        recipe = str(row['recipe']).upper()
        if recipe not in ('A', 'B', 'C'):
            raise ValueError(f'Unknown recipe {recipe}')
        record['recipe_B'] = int(recipe == 'B')
        record['recipe_C'] = int(recipe == 'C')
        for name in ROLLING:
            h = history[machine][name]
            h.append(record[name])
            vals = np.asarray(h, dtype=float)
            record[f'{name}_mean_3'] = float(vals.mean())
            record[f'{name}_std_3'] = float(vals.std())
        features.append([record[key] for key in FEATURES])
    X = np.asarray(features, dtype=float)
    if not np.isfinite(X).all():
        raise ValueError('Missing or non-finite numeric data')
    return X


def _classifier() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=180, max_depth=9, min_samples_leaf=4,
        class_weight='balanced', random_state=20261009, n_jobs=-1,
    )


def train(csv_path: str, model_path: str, metrics_path: str, test_fraction: float = .2, gap: int = 20) -> dict:
    """Chronological evaluation, then fit final model on all labeled rows.

    Unlabeled rows still contribute to preceding-window feature history.
    Expected data cadence is five minutes, as in the synthetic source data.
    """
    rows = sorted(load_csv(csv_path), key=lambda r: (datetime.fromisoformat(str(r['timestamp'])), r['machine_id']))
    X = feature_matrix(rows)
    labeled_indices = np.asarray([
        i for i, r in enumerate(rows) if str(r.get('health_label', '')).strip() in ('0', '1')
    ], dtype=int)
    if len(labeled_indices) < 100:
        raise ValueError('Need at least 100 labeled readings for this demo configuration')
    y_all = np.asarray([int(rows[i]['health_label']) for i in labeled_indices])
    if len(np.unique(y_all)) != 2:
        raise ValueError('Need verified examples of both label classes')
    # Split by time, with a 20-measurement embargo to reduce neighbor leakage.
    boundary = int(len(labeled_indices) * (1-test_fraction))
    cutoff = rows[labeled_indices[boundary]]['timestamp']
    test_idx = np.asarray([i for i in labeled_indices if rows[i]['timestamp'] >= cutoff])
    earlier = defaultdict(list)
    for i in labeled_indices:
        if rows[i]['timestamp'] < cutoff:
            earlier[rows[i]['machine_id']].append(i)
    # Embargo the final gap labeled observations of each machine, not just globally.
    train_idx = np.asarray(sorted(i for indices in earlier.values() for i in indices[:-gap]), dtype=int)
    if len(train_idx) < 20 or len(test_idx) < 10:
        raise ValueError('Not enough data for a chronological split')
    y_train = np.array([int(rows[i]['health_label']) for i in train_idx])
    y_test = np.array([int(rows[i]['health_label']) for i in test_idx])
    if len(set(y_train)) != 2 or len(set(y_test)) != 2:
        raise ValueError('Both classes needed in training and test periods; collect additional labeled periods')
    evaluation_model = _classifier()
    evaluation_model.fit(X[train_idx], y_train)
    predictions = evaluation_model.predict(X[test_idx])
    metrics = {
        'labeled_rows': len(labeled_indices),
        'training_rows_for_evaluation': len(train_idx),
        'embargo_labeled_rows': len(labeled_indices)-len(test_idx)-len(train_idx),
        'label_counts': {str(c): int((y_all == c).sum()) for c in (0,1)},
        'training_label_counts': {str(c): int((y_train == c).sum()) for c in (0,1)},
        'test_label_counts': {str(c): int((y_test == c).sum()) for c in (0,1)},
        'test_start': cutoff,
        'evaluation_config': {'test_fraction': test_fraction, 'gap_per_machine': gap},
        'deployed_training_rows': len(labeled_indices),
        'synthetic_only': True,
        'test_rows': len(test_idx),
        'accuracy': float(accuracy_score(y_test, predictions)),
        'balanced_accuracy': float(balanced_accuracy_score(y_test, predictions)),
        'confusion_matrix_label_order_0_1': confusion_matrix(y_test, predictions, labels=[0,1]).tolist(),
        'classification_report': classification_report(
            y_test, predictions, labels=[0,1], target_names=['Faulty','Healthy'],
            output_dict=True, zero_division=0),
        'note': 'Synthetic demo. Evaluation model used earlier periods; final model is retrained on all labeled rows.',
    }
    metrics.update({key: metrics['classification_report']['macro avg'][key] for key in ('precision','recall','f1-score')})
    metrics['limitation'] = 'Chronological holdout metrics describe the evaluation candidate, not an independent test of the final all-labeled model. Synthetic faults may be highly separable; these probabilities are not validated industrial risks.'
    # The final deployed model uses the newly added labeled data as well.
    final_model = _classifier()
    final_model.fit(X[labeled_indices], y_all)
    artifact = {
        'model': final_model, 'feature_names': FEATURES, 'window_size': 3,
        'class_mapping': LABELS, 'notice': 'SYNTHETIC DEMO ONLY — not machine safety diagnostics.',
    }
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    Path(metrics_path).write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    return metrics


def predict(rows: list[dict], model_path: str) -> list[dict]:
    """Batch prediction; use chronological rows including history before target row(s)."""
    artifact = joblib.load(model_path)  # Load ONLY trusted model artifacts.
    if artifact.get('feature_names') != FEATURES:
        raise ValueError('Incompatible feature schema / model version')
    X = feature_matrix(rows)
    labels = artifact['model'].predict(X)
    probability = artifact['model'].predict_proba(X)
    classes = list(artifact['model'].classes_)
    faulty_idx = classes.index(0)
    return [
        {
            'timestamp': r['timestamp'], 'machine_id': r['machine_id'],
            'predicted_health_label': int(label),
            'predicted_status': LABELS[int(label)],
            'fault_probability': round(float(p[faulty_idx]), 6),
        }
        for r, label, p in zip(rows, labels, probability)
    ]


def main() -> None:
    cli = argparse.ArgumentParser(description='Synthetic ZSK model for MCP backend integration')
    commands = cli.add_subparsers(dest='command', required=True)
    train_parser = commands.add_parser('train', help='Retrain model using all currently labeled rows')
    train_parser.add_argument('--data', required=True)
    train_parser.add_argument('--model', default='zsk_model.joblib')
    train_parser.add_argument('--metrics', default='zsk_metrics.json')
    batch_parser = commands.add_parser('batch', help='Predict ordered history in a CSV file')
    batch_parser.add_argument('--data', required=True)
    batch_parser.add_argument('--model', required=True)
    batch_parser.add_argument('--output', required=True)
    for parser in (commands.add_parser('predict', help='Predict last row (pass its preceding history)'),):
        parser.add_argument('--data', required=True)
        parser.add_argument('--model', required=True)
    args = cli.parse_args()
    if args.command == 'train':
        print(json.dumps(train(args.data, args.model, args.metrics), indent=2))
    else:
        rows = load_csv(args.data)
        outputs = predict(rows, args.model)
        if args.command == 'batch':
            save_csv(args.output, outputs)
            print(json.dumps({'processed_rows': len(outputs), 'output': args.output}))
        else:
            print(json.dumps(outputs[-1], indent=2))


if __name__ == '__main__':
    main()
