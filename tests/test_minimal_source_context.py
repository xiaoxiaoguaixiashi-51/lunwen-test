import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.minimal_source_context import context_parts, build_context


class MinimalSourceContextTest(unittest.TestCase):
    def method(self,root,code):
        path=root/'Outer.java';path.write_text(code,encoding='utf-8')
        return {'target':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'method':'work','method_owner':'p.Outer.Inner','method_parameter_types':['String']}

    def test_exact_owner_overload_and_braces_in_literals(self):
        code='''package p;
public class Outer {
 public int work(String s) { return 900; }
 public static class Inner {
  private int field;
  public Inner(int n) { field=n; }
  public int work(int n) { return 700; }
  public int work(String s) { String marker="} {"; /* } */ return help(s); }
  private int help(String s) { return s.length(); }
 }
}'''
        with tempfile.TemporaryDirectory() as directory:
            method=self.method(Path(directory),code)
            context=build_context(method,lambda text:True)
            self.assertIn('return help(s);',context['F1'])
            self.assertNotIn('return 900',context['F1'])
            self.assertNotIn('return 700',context['F1'])
            self.assertNotIn('return s.length()',context['F1'])
            self.assertIn('return s.length()',context['F2'])
            self.assertEqual(['String'],context['included_local_helpers'][0]['parameter_types'])

    def test_never_truncate_mandatory_focal_or_add_oversized_helper(self):
        code='''package p; public class Outer { public static class Inner {
 public int work(String s) { return help(s); }
 private int help(String s) { return s.length(); }
}}'''
        with tempfile.TemporaryDirectory() as directory:
            method=self.method(Path(directory),code)
            parts=context_parts(method)
            context=build_context(method,lambda text:len(text)<=len(parts['mandatory']))
            self.assertTrue(context['mandatory_fits'])
            self.assertEqual(context['F1'],context['F2'])
            self.assertEqual(1,len(context['excluded_local_helpers']))
            too_small=build_context(method,lambda text:False)
            self.assertFalse(too_small['mandatory_fits'])
            self.assertIn('return help(s);',too_small['F1'])

    def test_changed_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            method=self.method(Path(directory),'package p; class Outer { class Inner { int work(String s){return 1;} } }')
            Path(method['target']).write_text('changed')
            with self.assertRaises(ValueError):context_parts(method)

    def test_annotations_do_not_end_headers_at_literal_brace(self):
        code='''package p; public class Outer { @Tag("{") public static class Inner {
 @Tag("{") public Inner() {}
 @Tag("}") public int work(String s) { return 1; }
}}'''
        with tempfile.TemporaryDirectory() as directory:
            parts=context_parts(self.method(Path(directory),code))
            self.assertIn('@Tag("{") public static class Inner',parts['mandatory'])
            self.assertIn('@Tag("{") public Inner();',parts['mandatory'])
            self.assertIn('return 1;',parts['focal_text'])

    def test_generic_method_modifiers_survive_without_javadoc(self):
        code='''package p; public class Outer { public static class Inner {
 /** Existing method documentation. */
 public static <T> T work(String s) { return null; }
}}'''
        with tempfile.TemporaryDirectory() as directory:
            parts=context_parts(self.method(Path(directory),code))
            self.assertIn('public static <T> T work',parts['focal_text'])
            self.assertNotIn('Existing method documentation',parts['focal_text'])


if __name__=='__main__':unittest.main()
