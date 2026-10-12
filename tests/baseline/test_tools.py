import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]/'baseline'
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
cmp=module('compare');fixtures=module('fixtures');runner=module('run')

class Tools(unittest.TestCase):
    def test_float_tolerance(self):
        cmp.compare({'fps':1.0},{'fps':1.0+1e-10})
        for v in (1.0+1e-7,float('nan'),float('inf')):
            with self.assertRaises(AssertionError):cmp.compare({'fps':1.0},{'fps':v})
    def test_discrete_exact(self):
        for a,b in (({'duplicate':True},{'duplicate':1}),({'counts':[1]},{'counts':[2]}),
                    ({'tears':[[0,1],[1,2]]},{'tears':[[1,2],[0,1]]}),
                    ({'branch':'duplicate'},{'branch':'full'}),({'fps':0},{'fps':0,'x':0})):
            with self.assertRaises(AssertionError):cmp.compare(a,b)
    def test_fixture_reproducibility(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b'
            fixtures.generate(a);fixtures.generate(b)
            cmp.directories(a,b)
            manifest=json.loads((a/'manifest.json').read_text())
            for case in manifest['cases']:
                for stream in case['streams']:
                    for frame in stream:
                        data=(a/frame['path']).read_bytes()
                        self.assertEqual(len(data),case['width']*case['height']*3)
                        self.assertEqual(fixtures.hashlib.sha256(data).hexdigest(),frame['sha256'])
    def test_binary_and_missing_fail(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b';a.mkdir();b.mkdir()
            with self.assertRaises(AssertionError):cmp.directories(a,b)
            (a/'mask.bin').write_bytes(b'\0');(b/'mask.bin').write_bytes(b'\1')
            with self.assertRaises(AssertionError):cmp.directories(a,b)

    def test_export_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = fixtures.generate(Path(d)/'fixtures')
            cases = {case['id']: case for case in manifest['cases']}
            expected_rows = {'pipeline_csv': 4, 'pipeline_centered': 5,
                             'pipeline_redraw': 6}
            for name, rows in expected_rows.items():
                expected = runner.expected_exports(cases[name])
                self.assertEqual(expected['csv']['rows'], rows)
                self.assertEqual(expected['csv']['columns'], 2)
                output = Path(d)/name
                output.mkdir()
                with self.assertRaises(AssertionError):
                    runner.validate_exports(output, expected)
                csv_path = output/expected['csv']['name']
                csv_path.write_bytes(b'')
                with self.assertRaises(AssertionError):
                    runner.validate_exports(output, expected)
                csv_path.write_text('a,b\n' * rows)
                runner.validate_exports(output, expected)
                csv_path.write_text('a,b\n' * (rows - 1))
                with self.assertRaises(AssertionError):
                    runner.validate_exports(output, expected)
            expected = runner.expected_exports(cases['pipeline_images'])
            self.assertEqual(expected['images'],
                             [f'exportsequence_{i:010d}.jpg' for i in range(4)])
            output = Path(d)/'images'
            output.mkdir()
            for name in expected['images']:
                (output/name).write_bytes(b'nonempty test data')
            runner.validate_exports(output, expected)
            extra = output/'unexpected.jpg'
            extra.write_bytes(b'extra test data')
            with self.assertRaises(AssertionError):
                runner.validate_exports(output, expected)
            extra.unlink()
            (output/expected['images'][0]).write_bytes(b'')
            with self.assertRaises(AssertionError):
                runner.validate_exports(output, expected)
            (output/expected['images'][0]).unlink()
            with self.assertRaises(AssertionError):
                runner.validate_exports(output, expected)

    def test_matching_incomplete_exports_fail(self):
        with tempfile.TemporaryDirectory() as d:
            case = dict(streams=[[{}, {}]], pipeline=True, csv=True)
            result = dict(case='csv', exit_code=0, classification='regression',
                          expected_exports=runner.expected_exports(case))
            a, b = Path(d)/'a', Path(d)/'b'
            for root in (a, b):
                semantic = root/'csv'/'semantic'
                semantic.mkdir(parents=True)
                (semantic/'trace.json').write_text('{}')
                (root/'results.json').write_text(json.dumps([result]))
            with self.assertRaises(AssertionError):
                runner.suites(a, b)

if __name__=='__main__':unittest.main()
