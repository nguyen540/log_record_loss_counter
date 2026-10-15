# log_record_loss_counter

Wraps a `logging.Handler` and counts records dropped due to handler errors, flushing the count as a periodic summary record.

```python
import logging
from log_record_loss_counter import LossCountingHandler

file_handler = logging.FileHandler("app.log")
lossy = LossCountingHandler(file_handler, threshold=10)

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
logger.addHandler(lossy)

# If file_handler.emit raises (disk full, permission flip, etc.) on ten
# records, lossy injects a single WARNING summary into the same file:
#   "dropped 10 log record(s) due to handler errors"
```

## Why

A handler that fails silently is worse than no handler: the application believes its logs are landing somewhere, and they are not. Standard `logging` calls `handleError` on failure, which by default prints to stderr and moves on — fine for interactive runs, poor for long-lived services where stderr may be redirected to a different sink or rotated away.

This library makes loss observable at the destination itself: after a configured number of dropped records, it writes a single summary record through the wrapped handler. The trade-off is that if the wrapped handler is genuinely broken (disk full, network dead), the summary will also fail — at which point the loss is silent again. That is accepted: the goal is to surface *intermittent* failures (permission flips, transient resource limits) where the destination recovers and a summary can land.

## Edge cases

- A summary record that also raises does **not** zero the counter. The running loss count persists so the next threshold crossing still represents accumulated loss; without this, a persistently broken destination would summarise its own failure forever.
- Only one summary is flushed per threshold crossing, even if the accumulated loss is several multiples of the threshold. This keeps output steady and avoids flooding an already-struggling destination.
- `LossCountingHandler` does not participate in the standard `logging` level/filter machinery inherited from `logging.Handler`. It intentionally bypasses it so records are never silently dropped before reaching the wrapped handler; skipping `Handler.__init__` is deliberate.

## Tests

```
PYTHONPATH=src python -m unittest discover -s tests
```
