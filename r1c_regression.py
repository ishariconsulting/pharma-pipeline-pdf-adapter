"""Run synthetic safety checks and emit honest, data-blocked Gilead outcomes."""
import io
import json
from pathlib import Path
import unittest

from r1c_shared_lineage import blocked
from test_r1c_shared_lineage import SafetyTests


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = set()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.add(test._testMethodName)


def main():
    specs = json.loads((Path(__file__).parent / "audits/R1C_GILEAD_CASES.json").read_text())
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SafetyTests)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=RecordingResult).run(suite)
    report = blocked(["No official row-level Gilead snapshot was supplied"], 53, specs)
    report["syntheticSafetySuite"] = {"run": result.testsRun, "passed": len(result.passed),
                                      "failures": len(result.failures), "errors": len(result.errors),
                                      "skipped": len(result.skipped), "log": output.getvalue(),
                                      "fixtureType": "SYNTHETIC — NOT GILEAD OBSERVATIONS"}
    for case, spec in zip(report["cases"], specs):
        tests = ["test_" + name for name in spec["negativeChecks"]]
        case["syntheticSafetyChecks"] = {name: "PASS" if name in result.passed else "FAIL" for name in tests}
        case["acceptanceProof"] = "NOT RUN — source-key/record/arm snapshot required"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
