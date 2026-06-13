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

Automated coverage evidence packages:

```text
/root/rq1_pilot_real_v2_coverage_auto_v4_20260613.tar.gz
/root/rq1_pilot_real_v2_coverage_two_classes_20260613.tar.gz
```

Package size observed on AutoDL:

```text
runtime: 190K
coverage pilot: 22K
coverage auto LocaleUtils: 60K
coverage auto two classes: 61K
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

The next coverage run can use the automated runner. Start it inside `screen`
on AutoDL so the process survives SSH disconnects:

```bash
cd /root/lunwen-test
git -c http.version=HTTP/1.1 pull --ff-only
source .venv/bin/activate

screen -S rq1_coverage_localeutils
python scripts/run_defects4j_generated_coverage.py \
  --run-dir experiments/runs/rq1_pilot_real_v2 \
  --defects4j-dir /root/defects4j-work/Lang-1b \
  --output-dir experiments/runs/rq1_pilot_real_v2/coverage_check_auto_v1 \
  --default-package org.apache.commons.lang3 \
  --include-class-name LocaleUtils \
  --instrument-class org.apache.commons.lang3.LocaleUtils \
  --java-home /usr/lib/jvm/java-11-openjdk-amd64 \
  --overwrite
```

Expected outputs:

- `experiments/runs/rq1_pilot_real_v2/coverage_check_auto_v1/coverage_summary.csv`
- `experiments/runs/rq1_pilot_real_v2/coverage_check_auto_v1/coverage_summary.md`
- `experiments/runs/rq1_pilot_real_v2/coverage_check_auto_v1/coverage_class_summary.md`

## Automated Coverage Result

The coverage runner was validated on three generated test classes whose runtime pass rate was 100%.

| focal method | output_dir | covered | total | coverage_success_rate | max_line_coverage | max_condition_coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `LocaleUtils.toLocale` | `coverage_check_auto_v4` | 25 | 25 | 100.0% | 21.4% | 20.8% |
| `DateUtils.isSameLocalTime` | `coverage_check_auto_dateutils_v1` | 8 | 8 | 100.0% | 3.1% | 4.5% |
| `StringUtils.getLevenshteinDistance` | `coverage_check_auto_levenshtein_v1` | 13 | 13 | 100.0% | 1.9% | 1.1% |
| `NumberUtils.createNumber` | `coverage_check_auto_createnumber_v1` | 40 | 41 | 97.6% | 17.1% | 9.5% |
| **Total** |  | **86** | **87** | **98.9%** |  |  |

The successful two-class evidence package is:

```text
/root/rq1_pilot_real_v2_coverage_two_classes_20260613.tar.gz
```

Important implementation note: the Defects4J coverage runner now passes the instrument classes file as an absolute path. This is required because Defects4J executes inside the checked-out project directory, not the `/root/lunwen-test` repository directory.

The `NumberUtils.createNumber` run produced `40 covered` and `1 test_failed`. This matches its earlier runtime result of 40/41 and confirms that the coverage runner preserves test-failure classification instead of treating every completed Defects4J coverage command as successful coverage.

The single failed coverage method was:

```text
org.apache.commons.lang3.math.D4jGeneratedNumberUtilsCreateNumberTest::test_suffix_D_infinite_falls_to_big_decimal
```

It still produced coverage metrics:

```text
Lines covered: 54/375 = 14.4%
Conditions covered: 23/338 = 6.8%
```

Defects4J also emitted:

```text
WARNING: Some tests failed (see /root/defects4j-work/Lang-1b/failing_tests)!
```

## Current Interpretation

The current pilot supports two claims:

1. The generation, compilation, and feedback-repair chain is working on real Defects4J methods.
2. Compilation success alone is not sufficient; runtime validation exposes additional issues from project source-level constraints, test harness behavior, and behavioral oracle mismatches.
3. Defects4J coverage is usable for this pipeline, and the current pilot has verified both successful coverage collection and failure-aware classification across four generated test classes.

## Next Step

Keep the current result as the first runtime-validated pilot evidence. The next mainline task is to:

- identify and preserve the single `NumberUtils.createNumber` coverage failure, then
- run coverage for the remaining current pilot classes in batches before expanding to a larger Defects4J method set.
