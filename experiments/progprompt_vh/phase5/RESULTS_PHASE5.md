# Phase-5 Results

This report uses exactly one formal run for each of 10 test_unseen tasks × three frozen methods. No repeats or task selection were performed.

## Integrity

- Formal records: 30 unique task/method pairs; raw SHA-256 `b6d91c5da04e666ccf0eada583d70ad224d667fc99966ed49ebc1a6ffa8217a4`.
- Backend: ARK `doubao-seed-2-1-pro-260628`, Responses API, temperature 0, thinking disabled, max output 600.
- `verified_but_stopped_count`: 0.
- Frozen action/semantic/decomposition hashes match `PROTOCOL.md` in every record.

## Official

| Method | SR | GCR | Exec | Calls | Tokens |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-GraphCompatible | 0.300 | 0.716 | 0.903 | 9.8 | 5730.7 |
| HPAF-Flat | 0.500 | 0.677 | 0.983 | 1.0 | 1704.5 |
| HPAF-Hierarchical | 0.300 | 0.623 | 0.990 | 1.4 | 2365.3 |

Planning latency means (seconds/task): ProgPrompt-GraphCompatible=51.34, HPAF-Flat=3.97, HPAF-Hierarchical=6.14.

## Semantic

| Method | Semantic SR | Semantic GCR |
|---|---:|---:|
| ProgPrompt-GraphCompatible | 0.800 | 0.850 |
| HPAF-Flat | 1.000 | 1.000 |
| HPAF-Hierarchical | 1.000 | 1.000 |

## By horizon

Each cell is Semantic SR (Official SR). Long contains only two tasks and is descriptive, not a significance claim.

| Horizon | ProgPrompt-GraphCompatible | HPAF-Flat | HPAF-Hierarchical |
|---|---:|---:|---:|
| Short | 1.000 (0.000) | 1.000 (0.667) | 1.000 (0.000) |
| Medium | 0.600 (0.600) | 1.000 (0.600) | 1.000 (0.600) |
| Long | 1.000 (0.000) | 1.000 (0.000) | 1.000 (0.000) |

## Repair

| Method | First-pass atomic success | Retry rate | Post-repair atomic success |
|---|---:|---:|---:|
| HPAF-Hierarchical | 0.923 | 0.077 | 1.000 |

The hierarchy executed 13 atomics from 13 frozen atomics, used Retry-1 1 time(s), recovered 1.000 of retried atomics, and had 0 early stops.

## Interpretation

- RQ1 — **NOT SUPPORTED in this single-run controlled set.** Flat and Hierarchical both reached Semantic SR=1.000 overall and in every horizon, so explicit decomposition showed no completion-rate gain. This does not establish equivalence and the Long group has only two tasks.
- RQ2 — **SUPPORTED within the observed run.** One failed first pass was localized to the second atomic of the dual-object task; Retry-1 repaired it, execution continued, all 13 atomics finished, and verified-but-stopped stayed zero.
- Official and semantic metrics materially disagree. All methods reached Semantic SR=1.000 on Long while Official SR was 0.000; both views are retained. The frozen make-toast proxy also reverses the official/semantic outcome for ProgPrompt versus both HPAF variants, as disclosed before execution.
- ProgPrompt is much more expensive in calls/tokens because its assertion recovery performs additional state-check calls. HPAF-Hierarchical used more tokens than Flat when a task had multiple atomics or repair, but not enough to improve Semantic SR here.

## Plots

The `plots/` directory contains PNG and PDF versions of semantic SR/GCR, official SR, Exec by horizon, token cost, and hierarchical retry statistics. Rate plots use the full 0–1 y-axis.
