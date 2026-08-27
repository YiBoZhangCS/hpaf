# Failure Taxonomy

Offline categories are assigned from typed execution errors, missing frozen semantic conditions, and atomic accounting. No result was used to alter the frozen benchmark.

## ProgPrompt-Compat

- precondition_failure: 11 (test_unseen::wash_the_plate, test_unseen::bring_coffeepot_and_cupcake_to_the_coffee_table, env1::microwave_chicken, env1::watch_tv, env2::make_coffee_in_coffeemaker)
- wrong_relation: 8 (env1::bring_my_book_to_the_sofa, env1::bring_coffeepot_and_peach_to_the_coffee_table, vh40_long_s0_01, vh40_long_s0_03, vh40_long_s1_05)
- other: 3 (test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl, env1::wash_the_dishbowl_in_dishwasher, env2::wash_the_cutlery_in_dishwasher)

## HPAF-Flat

- verification_retry_failure: 10 (test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl, test_unseen::watch_tv, env1::watch_tv, env2::make_toast, env2::wash_the_cutlery_in_dishwasher)
- other: 2 (test_unseen::make_toast, env1::wash_the_dishbowl_in_dishwasher)
- process_lifecycle_incomplete: 1 (env1::microwave_chicken)

## HPAF-Full

- verification_retry_failure: 5 (test_unseen::wash_the_plate, test_unseen::watch_tv, env1::wash_the_dishbowl_in_dishwasher, env2::make_coffee_in_coffeemaker, vh40_long_s1_07)
- taskagent_parse_failure: 4 (vh40_long_s0_01, vh40_long_s1_05, vh40_long_s2_09, vh40_long_s2_11)
- other: 3 (vh40_long_s0_03, vh40_long_s0_04, vh40_long_s1_08)
