# Crucible L7 family I: atomic multi-entity writes (full, run 20261016T104743Z-i)

## I4a lost update (one counter)

| backend | mode | W | ops/writer | attempted | acked | final | lost (acked-final) | errors | retries |
|---|---|---|---|---|---|---|---|---|---|
| FalkorDB | pessimistic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 437463 |

## I4b write skew

| backend | mode | think ms | rounds | violations | errors | claimed-both | claimed-none |
|---|---|---|---|---|---|---|---|

