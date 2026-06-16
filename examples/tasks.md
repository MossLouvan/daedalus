# Example tasks to try

Daedalus boots with only `read_file`, `write_file`, and `list_dir`. Every task
below requires it to forge new tools to succeed. Run with:

```bash
daedalus "the task"
```

### Math / logic (forces it to build compute tools)
- `Compute the 30th Fibonacci number and tell me if it is prime.`
- `What is 17! (factorial) divided by 12!? Show the exact integer.`
- `Convert 255, 128, and 64 to hexadecimal and concatenate them.`

### Text / parsing
- `Count the word frequency in examples/tasks.md and report the top 5 words.`
- `Reverse every word in the sentence "the quick brown fox" but keep word order.`
- `Validate whether 'user@example.com' and 'not-an-email' are valid email addresses.`

### Data transforms (each forges a reusable tool)
- `Parse this CSV into JSON: name,age\nAda,36\nAlan,41 — write it to out.json.`
- `Given the numbers 4, 8, 15, 16, 23, 42, compute mean, median, and standard deviation.`

After a few runs, inspect what it built:

```bash
daedalus tools       # current toolbox
daedalus history     # every tool ever forged, and the task that triggered it
```
