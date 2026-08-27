# Long Task Structure Audit

All tasks were selected before any method execution. Each row has one semantic objective whose later stages depend on successful predecessor state; these are not independent `G1 AND G2 AND G3` compositions.

| Task | Scene | Category | Reference actions | Causal stages | Dependent stages | Independent goals | Rooms | Instruction |
|---|---:|---|---:|---:|---:|---:|---|---|
| `vh40_long_s0_01` | 0 | container_state_transfer | 15 | 6 | 5 | 1 | kitchen, livingroom | Temporarily store the creamybuns in the fridge, then transfer the creamybuns to the cabinet and leave both containers closed. |
| `vh40_long_s0_02` | 0 | appliance_lifecycle | 13 | 5 | 4 | 1 | bathroom, bedroom | Wash the slippers in the washingmachine, complete the cycle, then place the slippers on the bathroomcounter. |
| `vh40_long_s0_03` | 0 | causal_multi_object | 17 | 5 | 4 | 1 | kitchen | Stage the salmon and whippedcream together in the fridge, then leave the salmon stored there and deliver the whippedcream to the kitchencounter, with the fridge closed. |
| `vh40_long_s0_04` | 0 | cross_location_mixed | 17 | 5 | 4 | 1 | bathroom, bedroom | Stage the toothbrush on the bathroomcounter, store the toothbrush temporarily in the bathroomcabinet, then deliver the toothbrush to the bed and leave the bathroomcabinet closed. |
| `vh40_long_s1_05` | 1 | container_state_transfer | 15 | 6 | 5 | 1 | bathroom, bedroom, livingroom | Temporarily store the toothbrush in the cabinet, then transfer the toothbrush to the closet and leave both containers closed. |
| `vh40_long_s1_06` | 1 | appliance_lifecycle | 13 | 5 | 4 | 1 | kitchen | Clean the cookingpot in the dishwasher, complete the cycle, then place the cookingpot on the kitchentable. |
| `vh40_long_s1_07` | 1 | causal_multi_object | 17 | 5 | 4 | 1 | bathroom, bedroom | Stage the barsoap and toothbrush together in the bathroomcabinet, then leave the barsoap stored there and deliver the toothbrush to the bed, with the bathroomcabinet closed. |
| `vh40_long_s1_08` | 1 | cross_location_mixed | 17 | 5 | 4 | 1 | bathroom, bedroom, livingroom | Stage the toothpaste on the bed, store the toothpaste temporarily in the closet, then deliver the toothpaste to the bathroomcounter and leave the closet closed. |
| `vh40_long_s2_09` | 2 | container_state_transfer | 15 | 6 | 5 | 1 | bedroom, kitchen | Temporarily store the salmon in the fridge, then transfer the salmon to the cabinet and leave both containers closed. |
| `vh40_long_s2_10` | 2 | appliance_lifecycle | 13 | 5 | 4 | 1 | kitchen, livingroom | Heat the salmon in the microwave, complete the cycle, then place the salmon on the coffeetable. |
| `vh40_long_s2_11` | 2 | causal_multi_object | 17 | 5 | 4 | 1 | bathroom, livingroom | Stage the barsoap and slippers together in the cabinet, then leave the barsoap stored there and deliver the slippers to the bathroomcounter, with the cabinet closed. |
