"""Standard-library adversarial tests for the shipped houdini-wfc-workflow solver and resolver."""
from __future__ import annotations

import copy
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/houdini-wfc-workflow/scripts'))
import wfc

SCRIPT = ROOT / 'skills/houdini-wfc-workflow/scripts/wfc.py'
TEST_OUTPUT = os.environ.get('DSH_WFC_TEST_DIR')
DIRECTIONS = {
    'px': {'opposite': 'nx', 'delta': [1, 0, 0]},
    'nx': {'opposite': 'px', 'delta': [-1, 0, 0]},
}


def line_spec(size=3, **extra):
    value = {
        'schema_version': 1, 'shape': [size, 1, 1], 'directions': copy.deepcopy(DIRECTIONS),
        'modules': [
            {'id': 'L', 'sockets': {'px': 'b', 'nx': 'a'}},
            {'id': 'R', 'sockets': {'px': 'a', 'nx': 'b'}},
        ],
        'seed': 42,
    }
    value.update(extra)
    return value


def solve(spec, seed=None):
    return wfc.Solver(wfc.Problem(spec), {'max_seconds': 10}, seed).solve()


def make_catalog(styles, variants):
    return {'schema_version': 1, 'styles': {
        style: {'assets': {'tile': {'variants': items}}} for style, items in zip(styles, variants)
    }}


class SolverTests(unittest.TestCase):
    def test_reproducible_fixed_and_every_edge(self):
        spec = line_spec(constraints=[{'cell': [0, 0, 0], 'module': 'L'}])
        first = solve(spec)
        second = solve(spec)
        self.assertEqual(first['cells'], second['cells'])
        self.assertEqual([cell['module'] for cell in first['cells']], ['L@0', 'R@0', 'L@0'])
        self.assertEqual(wfc.verify_layout(wfc.Problem(spec), first)['edge_count'], 2)
        tampered = copy.deepcopy(first)
        tampered['cells'][1]['module'] = 'L@0'
        with self.assertRaisesRegex(wfc.WfcError, 'Fixed/boundary|Socket mismatch|State metadata'):
            wfc.verify_layout(wfc.Problem(spec), tampered)

    def test_yaw_rotates_sockets_without_multiplying_prototype_weight(self):
        spec = line_spec(1,
            directions={name: copy.deepcopy(value) for name, value in wfc.DEFAULT_DIRECTIONS.items()
                        if name in {'px', 'nx', 'pz', 'nz'}},
            modules=[{
                'id': 'wall', 'weight': 8, 'yaw_variants': [0, 90, 180, 270],
                'sockets': {'px': 'east', 'nx': 'west', 'pz': 'front', 'nz': 'back'},
            }])
        problem = wfc.Problem(spec)
        self.assertAlmostEqual(sum(state['weight'] for state in problem.states), 8)
        rotated = problem.states[problem.state_index['wall@90']]
        self.assertEqual(rotated['sockets'], {'px': 'front', 'nx': 'back', 'pz': 'west', 'nz': 'east'})
        self.assertEqual(wfc.rotate_y([1, 0, 0], 90), [0, 0, -1])
        self.assertEqual(wfc.rotate_y([0, 0, 1], 90), [1, 0, 0])
        quaternion = wfc.yaw_quaternion(90)
        self.assertAlmostEqual(quaternion[1], 2 ** .5 / 2)
        self.assertAlmostEqual(quaternion[3], 2 ** .5 / 2)

    def test_boundary_active_cells_and_tag_filters(self):
        spec = line_spec(active=[[0, 0, 0], [2, 0, 0]],
                         boundary_sockets={'nx': 'a', 'px': 'b'},
                         constraints=[{'cell': [2, 0, 0], 'exclude_tags': ['never']}])
        problem = wfc.Problem(spec)
        self.assertEqual(len(problem.edges), 0)
        result = solve(spec)
        self.assertEqual([cell['module'] for cell in result['cells']], ['L@0', 'L@0'])
        self.assertEqual(wfc.verify_layout(problem, result)['status'], 'valid')
        with self.assertRaisesRegex(wfc.WfcError, 'Socket mismatch|Fixed/boundary'):
            bad = copy.deepcopy(result)
            bad['cells'][0]['module'] = 'R@0'
            wfc.verify_layout(wfc.Problem(spec), bad)

    def test_forced_backtracking_restores_domains_and_budget_is_not_unsat(self):
        spec = line_spec(2, modules=[
            {'id': 'A', 'tags': ['first'], 'sockets': {'px': 'ab', 'nx': 'void'}},
            {'id': 'B', 'tags': ['second'], 'sockets': {'px': 'void', 'nx': 'ab'}},
            {'id': 'C', 'tags': ['second', 'cap'], 'sockets': {'px': 'void', 'nx': 'dc'}},
            {'id': 'D', 'tags': ['first', 'cap'], 'sockets': {'px': 'dc', 'nx': 'void'}},
        ], constraints=[
            {'cell': [0, 0, 0], 'require_tags': ['first']},
            {'cell': [1, 0, 0], 'require_tags': ['second']},
        ], counts=[{'tags': ['cap'], 'min': 1}])
        for seed in range(100):
            result = solve(spec, seed)
            self.assertEqual(result['status'], 'solved', result)
            self.assertEqual([cell['prototype'] for cell in result['cells']], ['D', 'C'])
            if result['statistics']['backtracks']:
                break
        else:
            self.fail('No seed exercised the forced count-propagation backtrack')
        limited = wfc.Solver(wfc.Problem(spec), {'max_seconds': 10, 'max_backtracks': 0}, seed).solve()
        self.assertEqual(limited['status'], 'budget_exceeded')
        self.assertEqual(limited['reason'], 'max_backtracks')

    def test_unsatisfiable_and_step_budget_are_distinct(self):
        impossible = line_spec(1, boundary_sockets={'px': 'not-a-socket'})
        self.assertEqual(solve(impossible)['status'], 'unsatisfiable')
        limited = wfc.Solver(wfc.Problem(line_spec()), {'max_seconds': 10, 'max_steps': 0}).solve()
        self.assertEqual(limited['status'], 'budget_exceeded')
        self.assertNotIn('cells', limited)
        fixed_empty = line_spec(1, constraints=[{'cell': [0, 0, 0], 'module': 'L', 'yaw': 90}])
        self.assertEqual(solve(fixed_empty)['status'], 'unsatisfiable')

    def test_count_bounds_and_connectivity_backtrack(self):
        spec = line_spec(modules=[
            {'id': 'off', 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'on', 'tags': ['on'], 'sockets': {'px': 'x', 'nx': 'x'}},
        ], counts=[{'id': 'two_on', 'tags': ['on'], 'min': 2, 'max': 2}],
            connectivity={'tags': ['on'], 'root': [1, 0, 0]})
        for seed in range(100):
            result = solve(spec, seed)
            self.assertEqual(result['status'], 'solved', result)
            self.assertEqual(wfc.verify_layout(wfc.Problem(spec), result)['status'], 'valid')
            on = [cell['index'] for cell in result['cells'] if cell['prototype'] == 'on']
            self.assertIn(1, on)
            self.assertEqual(max(on) - min(on), 1)
            if result['statistics']['global_conflicts']:
                break
        else:
            self.fail('No seed exercised final-connectivity backtracking')

    def test_arbitrary_graph_edges(self):
        spec = line_spec()
        spec.pop('shape')
        spec.update({
            'cells': [
                {'id': 'entry', 'coord': [0, 0, 0]},
                {'id': 'branch', 'coord': [2.5, 0, 1]},
                {'id': 'end', 'coord': [5, 0, -1]},
            ],
            'edges': [
                {'a': 'entry', 'direction': 'px', 'b': 'branch'},
                {'a': 'branch', 'direction': 'px', 'b': 'end'},
            ],
            'constraints': [{'cell': 'entry', 'module': 'L'}],
        })
        result = solve(spec)
        self.assertEqual([cell['module'] for cell in result['cells']], ['L@0', 'R@0', 'L@0'])
        self.assertEqual(wfc.verify_layout(wfc.Problem(spec), result)['edge_count'], 2)

    def test_custom_direction_names_preserve_unrotated_sockets(self):
        spec = line_spec(2, directions={
            'next': {'opposite': 'previous', 'delta': [1, 0, 0]},
            'previous': {'opposite': 'next', 'delta': [-1, 0, 0]},
        }, modules=[{'id': 'tile', 'sockets': {'next': 'x', 'previous': 'x'}}])
        result = solve(spec)
        self.assertEqual(result['status'], 'solved')
        self.assertEqual(wfc.verify_layout(wfc.Problem(spec), result)['edge_count'], 1)

    def test_sparse_active_domain_does_not_enumerate_empty_space(self):
        spec = line_spec(shape=[1000000, 1, 1000000],
                         active=[[999999, 0, 999999], [0, 0, 0]])
        result = solve(spec)
        self.assertEqual([cell['id'] for cell in result['cells']], ['0,0,0', '999999,0,999999'])
        self.assertEqual(wfc.verify_layout(wfc.Problem(spec), result)['edge_count'], 0)

    def test_count_membership_is_independent_of_remaining_state_count(self):
        modules = [
            {'id': 'off_a', 'tags': ['off'], 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'off_b', 'tags': ['off'], 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'on_a', 'tags': ['on'], 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'on_b', 'tags': ['on'], 'sockets': {'px': 'x', 'nx': 'x'}},
        ]
        spec = line_spec(2, modules=modules, constraints=[
            {'cell': [0, 0, 0], 'require_tags': ['off']},
            {'cell': [1, 0, 0], 'require_tags': ['on']},
        ], counts=[{'tags': ['on'], 'min': 1, 'max': 1}])
        result = solve(spec)
        self.assertEqual(result['status'], 'solved', result)
        self.assertEqual(wfc.verify_layout(wfc.Problem(spec), result)['status'], 'valid')
        # Two on states in a domain already contribute one definite on cell.
        spec['constraints'] = [{'cell': [0, 0, 0], 'require_tags': ['on']}]
        solver = wfc.Solver(wfc.Problem(spec))
        solver._propagate()
        self.assertEqual(solver.domains, [12, 3])

    def test_excluding_tags_means_any_tag_and_empty_list_excludes_nothing(self):
        spec = line_spec(1, modules=[
            {'id': 'a', 'tags': ['blocked'], 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'b', 'tags': ['water'], 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'c', 'sockets': {'px': 'x', 'nx': 'x'}},
        ], constraints=[{'cell': [0, 0, 0], 'exclude_tags': ['blocked', 'water']}])
        self.assertEqual(solve(spec)['cells'][0]['prototype'], 'c')
        spec['constraints'][0]['exclude_tags'] = []
        self.assertEqual(wfc.Problem(spec).initial, [7])

    def test_port_connectivity_distinguishes_adjacent_rooms_from_open_doors(self):
        spec = line_spec(2, modules=[
            {'id': 'sealed', 'tags': ['room'], 'sockets': {'px': 'wall', 'nx': 'wall'}},
            {'id': 'open', 'tags': ['room'], 'sockets': {'px': 'door_out', 'nx': 'door_in'}},
        ], socket_pairs=[['door_out', 'door_in']],
            constraints=[{'cell': [0, 0, 0], 'module': 'sealed'}],
            connectivity={'tags': ['room'], 'root': [0, 0, 0]})
        topology = solve(spec)
        self.assertEqual(topology['status'], 'solved')
        spec['connectivity']['sockets'] = ['door_out', 'door_in']
        self.assertEqual(solve(spec)['status'], 'unsatisfiable')
        # The independent verifier must enforce the port rule too.
        topology['spec_sha256'] = wfc.Problem(spec).spec_sha256
        with self.assertRaisesRegex(wfc.WfcError, 'Connectivity constraint failed'):
            wfc.verify_layout(wfc.Problem(spec), topology)
        spec['constraints'] = []
        opened = solve(spec)
        self.assertEqual([cell['prototype'] for cell in opened['cells']], ['open', 'open'])
        self.assertEqual(wfc.verify_layout(wfc.Problem(spec), opened)['status'], 'valid')

    def test_finite_extreme_weights_do_not_hang_candidate_selection(self):
        spec = line_spec(1, modules=[
            {'id': 'a', 'weight': 1e308, 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'b', 'weight': 1e308, 'sockets': {'px': 'x', 'nx': 'x'}},
            {'id': 'c', 'weight': 5e-324, 'sockets': {'px': 'x', 'nx': 'x'}},
        ])
        solver = wfc.Solver(wfc.Problem(spec))
        self.assertEqual(set(solver._ordered_candidates(7)), {0, 1, 2})
        self.assertEqual(solver.solve()['status'], 'solved')

    def test_independent_components_do_not_multiply_backtracking(self):
        spec = json.loads((ROOT / 'skills/houdini-wfc-workflow/assets/room-shell.spec.json').read_text(encoding='utf-8'))
        spec['shape'] = [16, 2, 16]
        spec.pop('counts')
        spec['budget'] = {'max_steps': 10000, 'max_backtracks': 200, 'max_seconds': 10}
        result = solve(spec)
        self.assertEqual(result['status'], 'solved', result)
        self.assertEqual(wfc.verify_layout(wfc.Problem(spec), result)['cell_count'], 512)
        self.assertLess(result['statistics']['backtracks'], 200)

    def test_bad_schema_and_layout_are_rejected(self):
        for mutate in (
            lambda value: value.update(shape=[0, 1, 1]),
            lambda value: value.update(active=[[-1, 0, 0]]),
            lambda value: value.update(active=[[0, 0, 0], [3, 0, 0]]),
            lambda value: value.update(unknown_option=True),
            lambda value: value['directions']['px'].update(opposite='missing'),
            lambda value: value['modules'][0].update(yaw_variants=[45]),
            lambda value: value['modules'][0].update(weight=0),
            lambda value: value.update(counts=[{'tags': ['L'], 'min': 2, 'max': 1}]),
        ):
            value = line_spec()
            mutate(value)
            with self.assertRaises(wfc.WfcError, msg=value):
                wfc.Problem(value)
        result = solve(line_spec())
        result['spec_sha256'] = '0' * 64
        with self.assertRaisesRegex(wfc.WfcError, 'different spec'):
            wfc.verify_layout(wfc.Problem(line_spec()), result)

    def test_random_small_cases_match_brute_force(self):
        rng = random.Random(8217)
        for case in range(40):
            size = rng.randint(2, 5)
            modules = []
            for index in range(rng.randint(2, 3)):
                modules.append({'id': f'm{index}', 'sockets': {
                    'px': rng.choice(['a', 'b']), 'nx': rng.choice(['a', 'b']),
                }})
            spec = line_spec(size, modules=modules, seed=case)
            if case % 3 == 0:
                spec['socket_pairs'] = [['a', 'b']]
            problem = wfc.Problem(spec)
            solutions = []
            for assignment in itertools.product(range(len(problem.states)), repeat=size):
                valid = True
                for a, direction, b in problem.edges:
                    opposite = problem.directions[direction]['opposite']
                    pair = (problem.states[assignment[a]]['sockets'][direction],
                            problem.states[assignment[b]]['sockets'][opposite])
                    if pair not in problem.pairs:
                        valid = False
                        break
                if valid:
                    solutions.append(assignment)
            result = solve(spec)
            if solutions:
                self.assertEqual(result['status'], 'solved', (case, result))
                self.assertEqual(wfc.verify_layout(problem, result)['status'], 'valid')
            else:
                self.assertEqual(result['status'], 'unsatisfiable', (case, result))

    def test_random_tag_counts_match_independent_exhaustive_search(self):
        rng = random.Random(51023)
        for case in range(60):
            size = rng.randint(2, 5)
            modules = [{'id': f'm{index}',
                        'tags': [tag for tag in ('red', 'green') if rng.choice([False, True])],
                        'sockets': {'px': rng.choice(['a', 'b']), 'nx': rng.choice(['a', 'b'])}}
                       for index in range(3)]
            counts = []
            for tags in (['red'], ['green'], ['red', 'green']):
                lower = rng.randint(0, size)
                counts.append({'tags': tags, 'min': lower, 'max': rng.randint(lower, size)})
            spec = line_spec(size, modules=modules, counts=counts)
            feasible = False
            for assignment in itertools.product(modules, repeat=size):
                if any(a['sockets']['px'] != b['sockets']['nx'] for a, b in zip(assignment, assignment[1:])):
                    continue
                if all(rule['min'] <= sum(set(rule['tags']).issubset(module['tags'])
                                         for module in assignment) <= rule['max'] for rule in counts):
                    feasible = True
                    break
            result = solve(spec)
            self.assertEqual(result['status'], 'solved' if feasible else 'unsatisfiable', (case, spec, result))
            if feasible:
                self.assertEqual(wfc.verify_layout(wfc.Problem(spec), result)['status'], 'valid')


class AssetResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dsh-wfc-', dir=TEST_OUTPUT)
        self.root = Path(self.temporary.name)
        for style in ('brick', 'stone'):
            for variant in ('v1', 'v2'):
                (self.root / f'{style}-{variant}.bgeo').write_text('fixture path only, not geometry', encoding='utf8')

    def tearDown(self):
        self.temporary.cleanup()

    def variant(self, style, variant_id='v1', **fit):
        return {
            'id': variant_id, 'asset': f'{style}-{variant_id}.bgeo', 'weight': 1,
            'bounds_min': [10, 20, 30], 'bounds_max': [14, 26, 34], 'anchor': [12, 20, 32],
            'fit': fit or {'mode': 'none'},
        }

    def test_style_hot_swap_preserves_structure_and_stable_variant_slots(self):
        spec = line_spec(cell_size=[2, 3, 1], modules=[{
            'id': 'tile', 'sockets': {'px': 'x', 'nx': 'x'},
        }])
        layout = solve(spec)
        catalog = make_catalog(['brick', 'stone'], [
            [self.variant('brick', 'v2'), self.variant('brick', 'v1')],
            [self.variant('stone', 'v1'), self.variant('stone', 'v2')],
        ])
        catalog_file = self.root / 'catalog.json'
        catalog_file.write_text(json.dumps(catalog), encoding='utf8')
        brick = wfc.resolve_instances(layout, catalog, 'brick', catalog_file)
        stone = wfc.resolve_instances(layout, catalog, 'stone', catalog_file)
        self.assertEqual([v['module'] for v in brick['instances']],
                         [v['module'] for v in stone['instances']])
        self.assertEqual([v['variant'] for v in brick['instances']],
                         [v['variant'] for v in stone['instances']])
        self.assertNotEqual(brick['instances'][0]['asset'], stone['instances'][0]['asset'])
        self.assertEqual(brick, wfc.resolve_instances(layout, catalog, 'brick', catalog_file))
        self.assertEqual(len(brick['prototypes']), len({v['piece'] for v in brick['instances']}))

    def test_nonuniform_bounds_fit_pivot_and_world_bounds(self):
        spec = line_spec(1, cell_size=[2, 3, 1], modules=[{
            'id': 'tile', 'sockets': {'px': 'x', 'nx': 'x'},
        }])
        layout = solve(spec)
        variant = self.variant('brick', mode='axes', target_size=[2, 3, 1],
                               min_scale=[.4, .4, .2], max_scale=[.6, .6, .3])
        catalog = make_catalog(['brick'], [[variant]])
        result = wfc.resolve_instances(layout, catalog, 'brick', self.root / 'catalog.json')
        instance = result['instances'][0]
        self.assertEqual(instance['scale'], [.5, .5, .25])
        self.assertEqual(instance['P'], [1, 0, .5])
        self.assertEqual(instance['pivot'], [12, 20, 32])
        self.assertEqual(instance['world_bounds'], {'min': [0, 0, 0], 'max': [2, 3, 1]})

    def test_target_size_is_explicit_and_uses_source_local_axes(self):
        spec = line_spec(1, cell_size=[4, 3, 2],
            directions={name: copy.deepcopy(value) for name, value in wfc.DEFAULT_DIRECTIONS.items()
                        if name in {'px', 'nx', 'pz', 'nz'}},
            modules=[{
                'id': 'tile', 'yaw_variants': [90],
                'sockets': {'px': 'x', 'nx': 'x', 'pz': 'x', 'nz': 'x'},
            }])
        layout = solve(spec)
        variant = self.variant('brick')
        variant.update(bounds_min=[0, 0, 0], bounds_max=[2, 1, 4], anchor=[1, 0, 2],
                       fit={'mode': 'axes', 'target_size': [2, 3, 4],
                            'min_scale': [1, 1, 1], 'max_scale': [1, 3, 1]})
        catalog = make_catalog(['brick'], [[variant]])
        instance = wfc.resolve_instances(layout, catalog, 'brick', self.root / 'catalog.json')['instances'][0]
        self.assertEqual(instance['fit']['target_size'], [2, 3, 4])
        self.assertEqual(instance['scale'], [1, 3, 1])
        self.assertEqual(instance['world_bounds'], {'min': [0, 0, 0], 'max': [4, 3, 2]})
        variant['fit'].pop('target_size')
        with self.assertRaisesRegex(wfc.WfcError, 'explicit local target_size'):
            wfc.resolve_instances(layout, catalog, 'brick', self.root / 'catalog.json')

    def test_mounting_envelope_preserves_overhang_and_external_anchor(self):
        spec = line_spec(2, cell_size=[4, 3, 4],
            directions={name: copy.deepcopy(value) for name, value in wfc.DEFAULT_DIRECTIONS.items()
                        if name in {'px', 'nx', 'pz', 'nz'}},
            modules=[{'id': 'tile', 'yaw_variants': [0, 90],
                      'sockets': {name: 'x' for name in ('px', 'nx', 'pz', 'nz')}}],
            constraints=[{'cell': [0, 0, 0], 'yaw': 0}, {'cell': [1, 0, 0], 'yaw': 90}])
        variant = self.variant('brick')
        variant.update(bounds_min=[-2, 0, -.3], bounds_max=[2, 3, .4], anchor=[0, 0, 1],
                       fit_bounds_min=[-1, 0, -.1], fit_bounds_max=[1, 3, .1],
                       fit={'mode': 'axes', 'target_size': [2, 3, .2]})
        catalog = make_catalog(['brick'], [[variant]])
        result = wfc.resolve_instances(solve(spec), catalog, 'brick', self.root / 'catalog.json')
        for instance in result['instances']:
            self.assertEqual(instance['scale'], [1, 1, 1])
            self.assertEqual(instance['fit']['source_size'], [2, 3, .2])
        for actual, expected in zip(result['instances'][0]['world_bounds']['min'], [0, 0, .7]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(result['instances'][1]['world_bounds']['max'], [5.4, 3, 4]):
            self.assertAlmostEqual(actual, expected)
        variant.pop('fit_bounds_max')
        with self.assertRaisesRegex(wfc.WfcError, 'declared together'):
            wfc.resolve_instances(solve(spec), catalog, 'brick', self.root / 'catalog.json')

    def test_scale_limit_missing_asset_and_bad_catalog_fail(self):
        spec = line_spec(1, cell_size=[2, 3, 1], modules=[{
            'id': 'tile', 'sockets': {'px': 'x', 'nx': 'x'},
        }])
        layout = solve(spec)
        variant = self.variant('brick', mode='axes', target_size=[2, 3, 1],
                               min_scale=[1, 1, 1], max_scale=[2, 2, 2])
        catalog = make_catalog(['brick'], [[variant]])
        with self.assertRaisesRegex(wfc.WfcError, 'scale tolerance') as caught:
            wfc.resolve_instances(layout, catalog, 'brick', self.root / 'catalog.json')
        self.assertEqual(caught.exception.code, 'scale_limit')
        variant['fit'] = {'mode': 'none'}
        variant['asset'] = 'missing.glb'
        with self.assertRaisesRegex(wfc.WfcError, 'does not exist'):
            wfc.resolve_instances(layout, catalog, 'brick', self.root / 'catalog.json')
        with self.assertRaisesRegex(wfc.WfcError, 'Unknown style'):
            wfc.resolve_instances(layout, catalog, 'modern', self.root / 'catalog.json')
        duplicate = make_catalog(['brick'], [[self.variant('brick'), self.variant('brick')]])
        with self.assertRaisesRegex(wfc.WfcError, 'Duplicate variant'):
            wfc.resolve_instances(layout, duplicate, 'brick', self.root / 'catalog.json')

    def test_cli_round_trip_and_overwrite_protection(self):
        spec_file = self.root / 'spec.json'
        layout_file = self.root / 'layout.json'
        cli_spec = line_spec(modules=[{'id': 'tile', 'sockets': {'px': 'x', 'nx': 'x'}}])
        spec_file.write_text(json.dumps(cli_spec), encoding='utf8')
        run = lambda *args: subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                                           text=True, capture_output=True, check=False)
        validated = run('validate', spec_file)
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
        solved = run('solve', spec_file, '--output', layout_file)
        self.assertEqual(solved.returncode, 0, solved.stdout + solved.stderr)
        original = layout_file.read_bytes()
        duplicate = run('solve', spec_file, '--output', layout_file)
        self.assertEqual(duplicate.returncode, 1)
        self.assertEqual(layout_file.read_bytes(), original)
        verified = run('verify', spec_file, layout_file)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        catalog = make_catalog(['brick'], [[self.variant('brick')]])
        catalog_file = self.root / 'catalog.json'
        catalog_file.write_text(json.dumps(catalog), encoding='utf8')
        output = self.root / 'instances.json'
        resolved = run('resolve', layout_file, '--catalog', catalog_file, '--style', 'brick', '--output', output)
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        self.assertEqual(json.loads(output.read_text(encoding='utf8'))['status'], 'resolved')


if __name__ == '__main__':
    unittest.main(verbosity=2)
