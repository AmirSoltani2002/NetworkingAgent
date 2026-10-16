"""Derive guide plots from exact saved sources; no inference or live DB writes."""
import ast
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(name, fields, rows):
    with (HERE / 'figures' / name).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    source = ROOT / 'zsk-service/data/zsk_labeled_1000.csv'
    with source.open() as stream:
        original = list(csv.DictReader(stream))
    start = datetime.fromisoformat(original[0]['timestamp'])
    history = []
    for row in original:
        history.append(dict(hours=(datetime.fromisoformat(row['timestamp']) - start).total_seconds() / 3600,
                            torque=row['screw_torque_pct'], vibration=row['gearbox_vibration_rms_mm_s'],
                            oil=row['gearbox_oil_temp_c'], label=row['health_label']))
    assert len(history) == 1000
    assert all(abs(b['hours'] - a['hours'] - 1/12) < 1e-10 for a, b in zip(history, history[1:]))
    old = list(csv.DictReader((HERE.parent / 'figures/measurements.csv').open()))
    assert len(old) == len(history)
    assert all(float(a[k]) == float(b[k]) for a, b in zip(old, history) for k in a)
    write_csv('history.csv', list(history[0]), history)

    trace_path = ROOT / 'docs/verification/factory/end-to-end.json'
    trace = json.loads(trace_path.read_text())
    operation = next(o for o in trace['task']['operations'] if o['action'].get('tool') == 'get_machine_measurements')
    result = operation['result']
    # Core stores the complete MCP response, including its structured content.
    print('measurement result keys:', list(result))
    data = result.get('structuredContent')
    if data is None and isinstance(result.get('output'), dict):
        data = result['output'].get('structuredContent')
    if data is None:
        raise ValueError('Missing exact structured sensor records')
    items = sorted(data['items'], key=lambda r: r['timestamp'])
    first = datetime.fromisoformat(items[0]['timestamp'])
    episode = [dict(minutes=(datetime.fromisoformat(r['timestamp']) - first).total_seconds()/60,
                    vibration=r['gearbox_vibration_rms_mm_s'], oil=r['gearbox_oil_temp_c'],
                    current=r['motor_current_a'], id=r['id'], timestamp=r['timestamp']) for r in items]
    assert len(episode) == 6
    assert all(b['minutes'] - a['minutes'] == 5 for a, b in zip(episode, episode[1:]))
    write_csv('episode.csv', list(episode[0]), episode)

    current_path = HERE.parent / 'evidence/zsk-final-state.json'
    forecast_path = ROOT / 'docs/verification/factory/forecast-metrics.json'
    current = json.loads(current_path.read_text())['metrics']['metrics']
    forecast = json.loads(forecast_path.read_text())['metrics']
    assert current['confusion_matrix_label_order_0_1'] == [[44, 2], [4, 150]]
    assert forecast['confusion_matrix_0_1'] == [[165, 5], [9, 21]]
    assert sum(map(sum, current['confusion_matrix_label_order_0_1'])) == current['test_rows'] == 200
    assert sum(map(sum, forecast['confusion_matrix_0_1'])) == forecast['test_rows'] == 200
    # Reproduce the guide's explicitly limited component-routing example.
    sys.path.insert(0, str(ROOT / 'zsk-service'))
    from zsk.synthetic import BASE, SCENARIOS, sensors
    worker_path = ROOT / 'factory-service/factory/worker.py'
    tree = ast.parse(worker_path.read_text())
    alarm = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'alarm')
    assignment = next(n for n in alarm.body if isinstance(n, ast.Assign) and
                      any(isinstance(t, ast.Name) and t.id == 'component' for t in n.targets))
    rule = compile(ast.Expression(assignment.value), 'source-component-rule', 'eval')
    routing = []
    for kind, (component, _, _) in SCENARIOS.items():
        target = sensors(60, [dict(fault_id=kind, start_minute=0, duration_minutes=60)], seed=13)
        selected = eval(rule, {'BASE': BASE, 'target': target})
        routing.append(dict(scenario=kind, scenario_component=component, selected_component=selected))
    assert [r['selected_component'] for r in routing] == ['gearbox', 'gearbox', 'motor', 'gearbox', 'barrel', 'die', 'barrel', 'motor']
    screenshot_paths = []
    for original_name, copy_name in [('factory-running.png', 'game-scene.png'),
                                     ('factory-component.png', 'game-inspector.png')]:
        original_path = ROOT / 'docs/verification/factory' / original_name
        copy_path = HERE / 'figures' / copy_name
        assert original_path.read_bytes() == copy_path.read_bytes()
        screenshot_paths.append(original_path)
    audit = {'historical_rows': len(history), 'cadence_minutes': 5,
             'first_timestamp': original[0]['timestamp'], 'last_timestamp': original[-1]['timestamp'],
             'recipe_boundaries_hours': [350/12, 700/12], 'original_plot_values_match': True,
             'episode_task_id': trace['task']['id'], 'episode_operation_id': operation['id'],
             'episode_records': episode, 'current_confusion_matrix': current['confusion_matrix_label_order_0_1'],
             'forecast_confusion_matrix': forecast['confusion_matrix_0_1'],
             'component_routing_at_minute_60_seed_13': routing,
             'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in (source, trace_path, current_path, forecast_path, worker_path, *screenshot_paths)},
             'limits': 'Saved synthetic evidence only. No fresh ML evaluation or agent run. No smoothing or resampling.'}
    (HERE / 'data-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print('Verified 1000 original rows, 6 episode rows, two matrices, 8 component routes, and unchanged screenshots.')


if __name__ == '__main__':
    main()
