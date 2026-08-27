# 04_full_success_ge3_atomic

- Task: `env1::watch_tv`
- Instruction: watch tv
- Scene: 1

## ProgPrompt-Compat

- Success: 0
- Exec: 0.818
- Tokens / calls: 4721 / 7
- Error: precondition_failure

### Timeline

1. PASS `comment` `# 0: walk to living room` 
2. PASS `action` `walk('livingroom')` 
3. PASS `comment` `# 1: find tv` 
4. PASS `action` `find('tv')` 
5. PASS `comment` `# 2: find remote control` 
6. PASS `action` `find('remotecontrol')` 
7. PASS `comment` `# 3: grab remote control` 
8. PASS `assert` `assert('close' to 'remotecontrol')` False
9. PASS `action` `find('remotecontrol')` 
10. PASS `action` `grab('remotecontrol')` 
11. PASS `comment` `# 4: turn on tv` 
12. PASS `assert` `assert('remotecontrol' in 'hands' )` True
13. PASS `recovery_skip` `else: find('remotecontrol')` assertion true
14. PASS `recovery_skip` `else: grab('remotecontrol')` assertion true
15. PASS `assert` `assert('close' to 'tv' )` False
16. PASS `action` `find('tv')` 
17. PASS `assert` `assert('tv' is 'switchoff' )` True
18. PASS `recovery_skip` `else: switchoff('tv')` assertion true
19. PASS `action` `switchon('tv')` 
20. PASS `comment` `# 5: find sofa` 
21. PASS `action` `find('sofa')` 
22. PASS `comment` `# 6: sit on sofa` 
23. PASS `assert` `assert('close' to 'sofa')` True
24. PASS `recovery_skip` `else: find('sofa')` assertion true
25. PASS `action` `sit('sofa')` 
26. PASS `comment` `# 7: watch tv` 
27. PASS `assert` `assert('tv' is 'switchon' )` False
28. FAIL `action` `switchon('tv')` <character> (1) is not close to <tv> (300) when executing "[SWITCHON] <tv> (300) [0]"
29. FAIL `action` `watch('tv')` <character> (1) is not close to <tv> (300) when executing "[SWITCHON] <tv> (300) [0]",<character> (1) does not face <tv> (300) when executing "[WATCH] <tv> (300) [0]"
30. PASS `comment` `# 8: Done` 

## HPAF-Flat

- Success: 0
- Exec: 0.000
- Tokens / calls: 2711 / 2
- Error: verifier_parse_failure

### Timeline

1. PASS `comment` `# move from kitchen to living room where tv is located` 
2. FAIL `action` `walk(livingroom)` bad arity for walk: expected 1, got 0
3. PASS `comment` `# locate the tv` 
4. FAIL `action` `find(tv)` bad arity for find: expected 1, got 0
5. PASS `comment` `# locate remote control to operate the tv` 
6. FAIL `action` `find(remotecontrol)` bad arity for find: expected 1, got 0
7. FAIL `action` `grab(remotecontrol)` bad arity for grab: expected 1, got 0
8. PASS `comment` `# power on the tv` 
9. FAIL `action` `switchon(tv)` bad arity for switchon: expected 1, got 0
10. PASS `comment` `# sit on the sofa to watch` 
11. FAIL `action` `sit(sofa)` bad arity for sit: expected 1, got 0
12. PASS `comment` `# look at and watch the tv` 
13. FAIL `action` `lookat(tv)` bad arity for lookat: expected 1, got 0
14. FAIL `action` `watch(tv)` bad arity for watch: expected 1, got 0

## HPAF-Full

- Success: 1
- Exec: 0.917
- Tokens / calls: 8665 / 9
- Error: verifier_parse_failure

### Timeline

1. PASS `comment` `# Move to the sofa and sit to prepare for watching TV` 
2. PASS `action` `find('sofa')` 
3. PASS `action` `walk('sofa')` 
4. PASS `action` `sit('sofa')` 
5. PASS `comment` `# Turn on the TV` 
6. PASS `action` `standup()` 
7. PASS `action` `find('tv')` 
8. PASS `action` `walk('tv')` 
9. PASS `action` `switchon('tv')` 
10. PASS `comment` `# Locate the powered-on TV in the living room` 
11. PASS `action` `find('tv')` 
12. PASS `comment` `# Watch the TV programming` 
13. FAIL `action` `watch('tv')` <character> (1) does not face <tv> (300) when executing "[WATCH] <tv> (300) [0]"
14. PASS `comment` `# repair` 
15. PASS `action` `find('tv')` 
16. PASS `action` `turnto('tv')` 
17. PASS `action` `watch('tv')` 
