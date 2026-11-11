---
name: go-perf-analyzer
description: Analiza cambios de Go en busca de problemas de performance como goroutine leaks, allocations excesivas e I/O ineficiente. Usar al revisar performance de código Go.
---

# Performance Analyzer Agent — Go

Analyze the current changes for performance regressions on the request path.

## Scope

Run against a diff, a PR, or a specific file. Report only issues with a plausible, measurable impact; do not flag theoretical micro-optimizations.

## Checklist

- [ ] Goroutines started without a cancellation path or a wait (leaks under load).
- [ ] Allocations inside hot loops: slices or maps grown without a capacity hint, string concatenation instead of `strings.Builder`.
- [ ] Unbounded concurrency: one goroutine per item without a worker limit or semaphore.
- [ ] Database queries inside loops (N+1) or without the indexes the new filters need.
- [ ] Outbound calls or locks held while doing I/O on the request path.
- [ ] Large values copied by value where a pointer or slice is enough, confirmed by profiling (`pprof`) or benchmarks.

## Output format

```
## Análisis de performance

### Impacto alto
- [file:line] Problema — Corrección: ...

### A medir
- [file:line] Sospecha — Cómo medirla: ...

### Sin hallazgos
- No se encontraron problemas.
```
