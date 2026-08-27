# VH-40 Provenance

VH-40 means the **VirtualHome 40-Task Evaluation Suite**, not an official 40-task ProgPrompt benchmark.

- Official-source component: 29 held-out task-scene instances from the pinned ProgPrompt/VirtualHome release. The original primary inventory is 70 instances: 35 train/example and 35 held-out candidates. The protocol retains 29 candidates with method-independent persistent or generic trace evaluation; six ambiguous held-out candidates remain excluded.
- Synthetic component: 11 pre-frozen long-horizon extensions on official scene inventories, generated deterministically with seed `20260826`, fixed templates, category/scene quotas, reference replay, and no method output. They are not official tasks.
- Total task-scene instances: 40; unique task texts: 35.
- Official task-unseen by exact train text: 24/29. Environment-held-out official instances: 20/29. Synthetic extensions are new instructions and separately labeled.
- Evaluators: 20 persistent-state, 9 frozen generic trace, 11 generic causal ordered-event plus final-state. All are method-independent and frozen before formal execution.

## Interview wording

“We evaluate on VH-40: 29 official-source held-out VirtualHome task-scene instances with method-independent scoring, plus 11 pre-frozen synthetic causal long-horizon extensions built on official VirtualHome scenes; all 40 are run once with three methods under a frozen evaluator.”
