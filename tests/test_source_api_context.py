import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.source_api_context import SourceIndex, build_api_context


class SourceApiContextTest(unittest.TestCase):
    def fixture(self, root):
        code = {
            'p/Base.java': 'package p; public abstract class Base { protected abstract String[] flatten(String s); public void base() {} }',
            'p/Target.java': '''package p; import q.Option;
public abstract class Target extends Base {
 protected void hiddenSetup() {} private void unavailable() {}
 public void work(Option option) { option.add("value"); }
 public void work(int other) {} }''',
            'q/Option.java': '''package q; public class Option {
 public Option(String name, boolean arg) {} public Option(String name, String desc) {}
 public void add(String v) { throw new IllegalArgumentException("BODY_NOT_AN_API_HEADER"); }
 private void privateMethod() {} }'''}
        for name, content in code.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in code}
        method = {'target': str(root / 'p/Target.java'), 'source_sha256': hashes['p/Target.java'],
                  'method': 'work', 'method_owner': 'p.Target', 'method_parameter_types': ['Option']}
        return SourceIndex(root, hashes), method, hashes

    def test_full_signatures_ancestors_and_dependency_overloads(self):
        with tempfile.TemporaryDirectory() as directory:
            index, method, _ = self.fixture(Path(directory))
            result = build_api_context(method, index, lambda text: True)
            self.assertIn('option.add("value");', result['F3'])
            self.assertIn('protected abstract String[] flatten(String s);', result['F3'])
            self.assertIn('public Option(String name, boolean arg);', result['F3'])
            self.assertIn('public Option(String name, String desc);', result['F3'])
            self.assertNotIn('BODY_NOT_AN_API_HEADER', result['F3'])
            self.assertNotIn('privateMethod', result['F3'])
            self.assertNotIn('private void unavailable', result['F3'])
            self.assertEqual({'p.Target', 'p.Base', 'q.Option'}, {r['type'] for r in result['included_api_types']})

    def test_budget_preserves_owner_and_ancestor_but_excludes_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            index, method, _ = self.fixture(Path(directory))
            result = build_api_context(method, index, lambda text: 'SOURCE API HEADERS: q.Option' not in text)
            self.assertTrue(result['mandatory_fits'])
            self.assertEqual(['q.Option'], [r['type'] for r in result['excluded_api_types']])
            too_small = build_api_context(method, index, lambda text: False)
            self.assertFalse(too_small['mandatory_fits'])
            self.assertIn('flatten(String s)', too_small['F3'])
            self.assertIn('option.add("value");', too_small['F3'])

    def test_changed_or_additional_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, hashes = self.fixture(root)
            (root / 'p/Base.java').write_text('class Changed {}')
            with self.assertRaisesRegex(ValueError, 'hash changed'):
                SourceIndex(root, hashes)
            (root / 'extra.java').write_text('class Extra {}')
            with self.assertRaisesRegex(ValueError, 'set differs'):
                SourceIndex(root, hashes)

    def test_ambiguous_wildcard_type_stays_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index, _, _ = self.fixture(root)
            index.types['r.Option'] = index.types['q.Option']
            import javalang
            origin = {'package': 's', 'tree': javalang.parse.parse('package s; import q.*; import r.*; class Origin {}')}
            self.assertIsNone(index.resolve('Option', origin))


if __name__ == '__main__':
    unittest.main()
