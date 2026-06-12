# RQ1 Pilot Runtime Report

## Scope

This report records the current RQ1 pilot result on Defects4J `Lang-1b`.

Dataset:

- 10 real focal methods selected from Defects4J `Lang-1b`
- Method list: `experiments/method_lists/rq1_pilot_real_v2.json`
- Runtime result directory: `experiments/runs/rq1_pilot_real_v2/runtime_check_auto_v5`

## Evidence Package

AutoDL evidence package:

```text
/root/rq1_pilot_real_v2_runtime_v5_20260612.tar.gz
```

Coverage pilot evidence package:

```text
/root/rq1_pilot_real_v2_coverage_pilot_20260612.tar.gz
```

Package size observed on AutoDL:

```text
runtime: 190K
coverage pilot: 22K
```

## Compilation Result

The generation and compilation-feedback stage completed for all 10 focal methods:

```text
Compilation Pass Rate = 10/10 = 100.0%
```

## Runtime Result

Generated JUnit test methods were executed inside a clean Defects4J `Lang-1b` checkout with Java 11.

```text
Runtime Pass Rate = 128/170 = 75.3%
```

Class-level runtime summary:

| test_class | passed | total | pass_rate |
| --- | ---: | ---: | ---: |
| org.apache.commons.lang3.D4jGeneratedClassUtilsGetPublicMethodTest | 2 | 7 | 28.6% |
| org.apache.commons.lang3.D4jGeneratedClassUtilsTest | 0 | 13 | 0.0% |
| org.apache.commons.lang3.D4jGeneratedCsvEscaperTranslateTest | 5 | 7 | 71.4% |
| org.apache.commons.lang3.D4jGeneratedGetLevenshteinDistanceTest | 13 | 13 | 100.0% |
| org.apache.commons.lang3.D4jGeneratedLocaleUtilsToLocaleTest | 25 | 25 | 100.0% |
| org.apache.commons.lang3.D4jGeneratedStringUtilsSubstringsBetweenTest | 15 | 18 | 83.3% |
| org.apache.commons.lang3.math.D4jGeneratedCreateBigIntegerTest | 20 | 25 | 80.0% |
| org.apache.commons.lang3.math.D4jGeneratedNumberUtilsCreateNumberTest | 40 | 41 | 97.6% |
| org.apache.commons.lang3.text.D4jGeneratedExtendedMessageFormatApplyPatternTest | 0 | 13 | 0.0% |
| org.apache.commons.lang3.time.D4jGeneratedDateUtilsIsSameLocalTimeTest | 8 | 8 | 100.0% |
| **Total** | **128** | **170** | **75.3%** |

## Failure Summary

Runtime failures:

| category | count |
| --- | ---: |
| compile_failure | 26 |
| compile_or_harness_failure | 1 |
| test_failure_unspecified | 15 |
| **Total** | **42** |

Observed failure evidence includes Java source-level incompatibility in the Defects4J test compile stage, for example:

```text
diamond operator is not supported in -source 6
```

## Coverage Pilot

A coverage pilot was completed for `LocaleUtils.toLocale` using Defects4J's built-in coverage command:

```text
defects4j coverage -t <Class::method> -i <instrument_classes>
```

The pilot instruments:

```text
org.apache.commons.lang3.LocaleUtils
```

Coverage was measured for the 25 generated methods in:

```text
org.apache.commons.lang3.D4jGeneratedLocaleUtilsToLocaleTest
```

Coverage outputs:

- `experiments/runs/rq1_pilot_real_v2/coverage_check/localeutils_methods`
- `experiments/runs/rq1_pilot_real_v2/coverage_check/localeutils_coverage_summary.csv`
- `experiments/runs/rq1_pilot_real_v2/coverage_check/localeutils_coverage_summary.md`

Observed single-test-method coverage range:

| metric | min | max |
| --- | ---: | ---: |
| Line coverage | 4.1% | 21.4% |
| Condition coverage | 1.4% | 20.8% |

Representative high-coverage method:

```text
org.apache.commons.lang3.D4jGeneratedLocaleUtilsToLocaleTest::test_valid_language_country_variant
Lines covered: 21/98 = 21.4%
Conditions covered: 15/72 = 20.8%
```

Environment note: Defects4J `Lang-1b` must run with Java 11. On AutoDL, force it before coverage commands:

```bash
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
hash -r
```

## Current Interpretation

The current pilot supports two claims:

1. The generation, compilation, and feedback-repair chain is working on real Defects4J methods.
2. Compilation success alone is not sufficient; runtime validation exposes additional issues from project source-level constraints, test harness behavior, and behavioral oracle mismatches.
3. Defects4J coverage is usable for this pipeline, and the current pilot has verified the measurement chain on one generated test class.

## Next Step

Keep the current result as the first runtime-validated pilot evidence. The next mainline task is to:

- extend coverage measurement from the `LocaleUtils.toLocale` pilot to class-level or aggregate coverage for the current 10-method pilot, then
- expand runtime and coverage validation to a larger Defects4J method set.
