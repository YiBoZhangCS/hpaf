# 02_full_success_flat_fail

- Task: `env1::microwave_chicken`
- Instruction: microwave chicken
- Scene: 1

## ProgPrompt-Compat

- Success: 0
- Exec: 0.375
- Tokens / calls: 9261 / 17
- Error: precondition_failure

### Timeline

1. PASS `comment` `# 0: walk to kitchen` 
2. PASS `action` `walk('kitchen')` 
3. PASS `comment` `# 1: find microwave` 
4. PASS `action` `find('microwave')` 
5. PASS `comment` `# 2: open microwave` 
6. PASS `assert` `assert('close' to 'microwave' )` True
7. PASS `recovery_skip` `else: find('microwave')` assertion true
8. PASS `assert` `assert('microwave' is 'closed' )` True
9. PASS `recovery_skip` `else: close('microwave')` assertion true
10. PASS `action` `open('microwave')` 
11. PASS `comment` `# 3: grab chicken` 
12. PASS `action` `find('chicken')` 
13. PASS `assert` `assert('close' to 'chicken')` True
14. PASS `recovery_skip` `else: find('chicken')` assertion true
15. PASS `action` `grab('chicken')` 
16. PASS `comment` `# 4: put chicken in microwave` 
17. PASS `assert` `assert('chicken' in 'hands' )` True
18. PASS `recovery_skip` `else: find('chicken')` assertion true
19. PASS `recovery_skip` `else: grab('chicken')` assertion true
20. PASS `assert` `assert('close' to 'microwave' )` True
21. PASS `recovery_skip` `else: find('microwave')` assertion true
22. PASS `assert` `assert('microwave' is 'opened' )` False
23. FAIL `action` `open('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]"
24. FAIL `action` `putin('chicken', 'microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]"
25. PASS `comment` `# 5: close microwave` 
26. PASS `assert` `assert('close' to 'microwave' )` True
27. PASS `recovery_skip` `else: find('microwave')` assertion true
28. PASS `assert` `assert('microwave' is 'opened' )` False
29. FAIL `action` `open('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]"
30. FAIL `action` `close('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[CLOSE] <microwave> (234) [0]"
31. PASS `comment` `# 6: turn on microwave` 
32. PASS `assert` `assert('close' to 'microwave' )` True
33. PASS `recovery_skip` `else: find('microwave')` assertion true
34. PASS `assert` `assert('microwave' is 'closed' )` True
35. PASS `recovery_skip` `else: close('microwave')` assertion true
36. FAIL `action` `switchon('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[CLOSE] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]"
37. PASS `comment` `# 7: wait for chicken to cook (watch microwave)` 
38. FAIL `action` `watch('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[CLOSE] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<microwave> (234) not lookable when executing "[WATCH] <microwave> (234) [0]"
39. PASS `comment` `# 8: turn off microwave` 
40. PASS `assert` `assert('close' to 'microwave' )` True
41. PASS `recovery_skip` `else: find('microwave')` assertion true
42. PASS `assert` `assert('microwave' is 'switchon' )` False
43. FAIL `action` `switchon('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[CLOSE] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<microwave> (234) not lookable when executing "[WATCH] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]"
44. FAIL `action` `switchoff('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[CLOSE] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<microwave> (234) not lookable when executing "[WATCH] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHOFF] <microwave> (234) [0]"
45. PASS `comment` `# 9: open microwave` 
46. PASS `assert` `assert('close' to 'microwave' )` True
47. PASS `recovery_skip` `else: find('microwave')` assertion true
48. PASS `assert` `assert('microwave' is 'closed' )` True
49. PASS `recovery_skip` `else: close('microwave')` assertion true
50. FAIL `action` `open('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[CLOSE] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<microwave> (234) not lookable when executing "[WATCH] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHOFF] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]"
51. PASS `comment` `# 10: grab cooked chicken` 
52. PASS `assert` `assert('close' to 'microwave' )` True
53. PASS `recovery_skip` `else: find('microwave')` assertion true
54. PASS `assert` `assert('microwave' is 'opened' )` False
55. FAIL `action` `open('microwave')` <character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[PUTIN] <chicken> (241) <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[CLOSE] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<microwave> (234) not lookable when executing "[WATCH] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHON] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[SWITCHOFF] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]",<character> (1) is not close to <microwave> (234) when executing "[OPEN] <microwave> (234) [0]"
56. PASS `action` `grab('chicken')` 
57. PASS `comment` `# 11: Done` 

## HPAF-Flat

- Success: 0
- Exec: 1.000
- Tokens / calls: 2358 / 2
- Error: none

### Timeline

1. PASS `comment` `# Locate and open the fridge to access chicken` 
2. PASS `action` `find('fridge')` 
3. PASS `action` `open('fridge')` 
4. PASS `comment` `# Acquire chicken from the fridge` 
5. PASS `action` `find('chicken')` 
6. PASS `action` `grab('chicken')` 
7. PASS `comment` `# Locate the microwave and open it to place chicken inside` 
8. PASS `action` `find('microwave')` 
9. PASS `action` `open('microwave')` 
10. PASS `action` `putin('chicken','microwave')` 
11. PASS `comment` `# Close and run the microwave to heat the chicken` 
12. PASS `action` `close('microwave')` 
13. PASS `action` `run('microwave')` 
14. PASS `comment` `# Complete the process by opening the microwave after heating` 
15. PASS `action` `open('microwave')` 

## HPAF-Full

- Success: 1
- Exec: 1.000
- Tokens / calls: 5162 / 5
- Error: none

### Timeline

1. PASS `comment` `# Locate and retrieve the chicken` 
2. PASS `action` `find('chicken')` 
3. PASS `action` `grab('chicken')` 
4. PASS `comment` `# Locate the microwave and open it before placing chicken inside` 
5. PASS `action` `find('microwave')` 
6. PASS `action` `open('microwave')` 
7. PASS `action` `putin('chicken', 'microwave')` 
8. PASS `action` `close('microwave')` 
9. PASS `comment` `# Locate the microwave containing the chicken` 
10. PASS `action` `find('microwave')` 
11. PASS `comment` `# Start the microwave to cook the chicken` 
12. PASS `action` `switchon('microwave')` 
13. PASS `comment` `# Complete the cooking process by turning the microwave off` 
14. PASS `action` `switchoff('microwave')` 
