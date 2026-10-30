import unittest

from scripts.run_kcf_utg_feedback import adapted_args


class KcfUtgEntrypointTest(unittest.TestCase):
    def test_adds_route_defaults(self):
        args = adapted_args(["--method-list", "methods.json"])
        self.assertEqual("config/config.kcf_utg.yaml", args[args.index("--config") + 1])
        self.assertEqual("KCF_UTG", args[args.index("--approach-name") + 1])
        self.assertIn("--exact-exec-union", args)

    def test_preserves_explicit_values(self):
        args = adapted_args([
            "--method-list", "methods.json",
            "--config", "custom.yaml",
            "--approach-name", "KCF_UTG_DEV",
        ])
        self.assertEqual(1, args.count("--config"))
        self.assertEqual(1, args.count("--approach-name"))
        self.assertIn("custom.yaml", args)
        self.assertIn("KCF_UTG_DEV", args)

    def test_does_not_duplicate_exact_scoring_flag(self):
        args = adapted_args(["--method-list", "methods.json", "--exact-exec-union"])
        self.assertEqual(1, args.count("--exact-exec-union"))


if __name__ == "__main__":
    unittest.main()
