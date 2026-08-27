# Phase-4 result tables

`GCR` is the display name for the released evaluator's raw `PSR` field.

## Overall

| Method | SR | GCR | Exec | Avg LLM Calls | Avg Tokens |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-Full | 0.500 | 0.726 | 0.711 | 10.20 | 5199.9 |
| HPAF-Decomp-Static | 0.300 | 0.616 | 0.865 | 5.50 | 7256.2 |
| HPAF-Decomp-ClosedLoop | 0.100 | 0.305 | 0.831 | 3.60 | 4406.0 |

## By horizon

| Horizon | Method | SR | GCR | Exec |
|---|---:|---:|---:|---:|
| Short | ProgPrompt-Full | 0.333 | 0.556 | 0.652 |
| Short | HPAF-Decomp-Static | 0.000 | 0.569 | 0.906 |
| Short | HPAF-Decomp-ClosedLoop | 0.333 | 0.667 | 0.826 |
| Medium | ProgPrompt-Full | 0.600 | 0.852 | 0.748 |
| Medium | HPAF-Decomp-Static | 0.600 | 0.853 | 0.872 |
| Medium | HPAF-Decomp-ClosedLoop | 0.000 | 0.210 | 0.811 |
| Long | ProgPrompt-Full | 0.500 | 0.667 | 0.708 |
| Long | HPAF-Decomp-Static | 0.000 | 0.091 | 0.787 |
| Long | HPAF-Decomp-ClosedLoop | 0.000 | 0.000 | 0.889 |
