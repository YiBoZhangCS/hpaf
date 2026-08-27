# Phase-6 Results

Exactly 20 frozen held-out task-scene instances × 3 methods × one formal run; 60 unique records. Raw SHA-256 `4197aa59a2851be3f96fbcce0a9016567b27952987f5a7754e4bcd75baefe75e`.

## Resume-oriented main table

| Method | Overall SR ↑ | Long SR ↑ | Exec ↑ | Avg Tokens / Task ↓ | Avg Calls / Task |
|---|---:|---:|---:|---:|---:|
| ProgPrompt | 0.800 | 0.750 | 0.918 | 5115.5 | 8.60 |
| HPAF-Flat | 0.750 | 0.500 | 0.935 | 2382.3 | 2.00 |
| HPAF-Full | 0.950 | 0.750 | 0.960 | 4404.4 | 4.00 |

## HPAF-Full relative to ProgPrompt

- overall_sr_absolute_percentage_points: 15.000000
- overall_sr_relative: 0.187500
- long_sr_absolute_percentage_points: 0.000000
- long_sr_relative: 0.000000
- exec_absolute_percentage_points: 4.125487
- token_reduction: 0.139009
- call_reduction: 0.534884

## Horizon

| Horizon | #Tasks | ProgPrompt SR | HPAF-Flat SR | HPAF-Full SR |
|---|---:|---:|---:|---:|
| Short | 6 | 0.667 | 1.000 | 1.000 |
| Medium | 10 | 0.900 | 0.700 | 1.000 |
| Long | 4 | 0.750 | 0.500 | 0.750 |

## Supplementary

The complete official metrics, semantic GCR, latency, repair, atomic, and per-role cost breakdown is in `results/summary_supplementary.csv`.
