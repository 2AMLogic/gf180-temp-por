"""Guard: `make test` must list every tests directory under sim/layout/signoff.

Run: python3 -m unittest discover -s sim/tests -t sim/tests -v
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class MakeTestListsSuites(unittest.TestCase):
    def test_every_tests_dir_is_in_make_test(self):
        makefile = (ROOT / "Makefile").read_text()
        for d in sorted(ROOT.glob("*/tests")):
            if not d.is_dir() or not any(d.glob("test_*.py")):
                continue
            rel = d.relative_to(ROOT).as_posix()
            self.assertIn(
                f"-s {rel} -t {rel}", makefile,
                f"{rel} has tests but `make test` does not run it",
            )


if __name__ == "__main__":
    unittest.main()
