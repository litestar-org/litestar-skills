# SQLglot Best Practices (v30+)

## Guardrails (Correctness + Performance)

- **Parse Once**: Reuse AST objects where possible.
- **Explicit Dialects**: Always set explicit source and target dialects (`read=...`, `write=...`); do not rely on default dialect inference.
- **Strict Handling**: Use strict unsupported handling in safety-critical paths:
  - `unsupported_level=ErrorLevel.RAISE` (or `IMMEDIATE`).
- **Compiled Version**: Prefer compiled SQLGlot install for throughput-sensitive workloads:
  - `sqlglot[c]`
- **CRITICAL (v30+)**: Do not use `sqlglot[rs]` (upstream-deprecated/incompatible path).
- **CRITICAL (v30+)**: Use `exp.Expr` for typing, not the deprecated `Expression`.
- **CRITICAL (v30+)**: Use DFS traversal when crawling AST nodes; BFS scope traversal module splits have changed in v30+. Avoid direct `scope.walk` without understanding the new module layout.
- **Opt-in Optimizer**: Treat heavy optimizer passes (`qualify`, `annotate_types`, full `optimize`) as opt-in due to schema/type overhead.
- **No Executor**: Do not use SQLGlot's built-in executor for high-throughput execution paths.
- **Dateutil Dependency**: If using optimizer interval simplification logic, ensure `python-dateutil` is installed.
- **Shims**: Lean on `SQL.ensure_expression` before importing sqlglot directly.
- **Caching**: Cache constant fragments at module scope.
- **Mutation Style**: Use `copy=False` for builder mutations (MANDATORY project default).

---

## Core Patterns

```python
from sqlglot import ErrorLevel, exp, parse_one, select, transpile

sql_out = transpile(
    sql,
    read="source_dialect",
    write="target_dialect",
    unsupported_level=ErrorLevel.RAISE,
)[0]

parsed = parse_one(sql, read="dialect")
constructed = select("*").from_("users").where("id = 1")
```

### Avoid Unnecessary Copies (MANDATORY)

Mutate in-place with `copy=False`:

```python
predicate = parse_one("user_id = :id")
query = select("*").from_("users").where(predicate, copy=False)
```

Avoid `copy=True` as it triggers a deep clone of the expression tree:

```python
query_slow = select("*").from_("users").where(predicate, copy=True)
```

**Why copy=False**:

- Deep copies walk the entire expression tree and allocate new nodes; 5-20x slower.
- SQLSpec builders expect mutable expressions.
- Only use `copy=True` when crossing thread boundaries.

---

## Pitfalls to Avoid

- Repeated parsing inside hot paths.
- Manual string manipulation for transpiling.
- Forgetting dialect context in `parse_one`.
- Running every optimizer pass.
- Importing sqlglot inside functions.
- Using `copy=True` (defeats AST reuse).
