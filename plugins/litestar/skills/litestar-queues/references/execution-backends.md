# litestar-queues — Execution Backends Reference

An execution backend decides **where a claimed task runs**. It never owns queue
state: arguments, task names, results, retries, schedules, and leases always
stay in the queue backend.

| Backend | Worker process | Transport carries |
| --- | --- | --- |
| `"local"` | Yes, in-process pool | Nothing (direct call) |
| `"immediate"` | No — runs inline at enqueue | Nothing |
| `CloudRunExecutionConfig` | Per-task Cloud Run Job execution | Record id via env |
| `CloudTasksExecutionConfig` | None anywhere | Record id only |
| `SqsExecutionConfig` | Long-polling consumers | Record id only |

## Local and Immediate

`"local"` is the default: workers claim records and run them in-process, honoring
`WorkerConfig.max_concurrency` and the bounded sync thread pool.

`"immediate"` runs the task inline at enqueue time and is intended for tests and
scripts. It requires `placement="external"`, because no worker owns the record.

## Google Cloud Run Jobs

```python
from litestar_queues import QueueConfig
from litestar_queues.execution.cloudrun import CloudRunExecutionConfig

queue_config = QueueConfig(
    queue_backend=...,  # any persistent backend
    execution_backend=CloudRunExecutionConfig(
        project_id="example-project",
        region="us-central1",
        job_name="worker-job",
        timeout=900,
    ),
)
```

Each claimed record triggers an isolated Cloud Run Job execution. Use
`profiles` for per-task resource shapes and `fallback_execution_backend` to
degrade to local execution when the API is unavailable.

## Google Cloud Tasks

Installed with `pip install "litestar-queues[cloud-tasks]"`.

A queue configured for Cloud Tasks keeps **no worker process anywhere**. Google
holds each record's delivery and calls a private consumer route when it is due,
so every process can scale to zero between deliveries. Only the record's id
crosses the network; arguments, metadata, and results are re-read from the queue
store by the consumer.

```python
from litestar_queues import QueueConfig
from litestar_queues.execution.cloudtasks import CloudTasksExecutionConfig

queue_config = QueueConfig(
    queue_backend=...,  # shared persistent backend
    execution_backend=CloudTasksExecutionConfig(
        project_id="example-project",
        location="us-central1",
        queue_id="default",
        service_url="https://api.example.com",
        service_account_email="queues@example-project.iam.gserviceaccount.com",
        dispatch_deadline=600,
    ),
)
```

The delivery route is registered at `/_litestar-queues/cloud-tasks` when the
execution backend is Cloud Tasks. It requires **either** Cloud Run's own IAM
asserted explicitly (`trust_platform_auth`) **or** your `guards`. It never
treats a delivery header as authentication.

## Amazon SQS

Installed with `pip install "litestar-queues[sqs]"`.

Run one dispatcher alongside any number of long-polling consumers against the
same persistent queue backend. Standard queues are the default; `fifo=True`
selects a FIFO queue.

```python
from litestar_queues import QueueConfig
from litestar_queues.execution.sqs import SqsExecutionConfig

queue_config = QueueConfig(
    queue_backend=...,  # shared persistent backend
    execution_backend=SqsExecutionConfig(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/tasks",
        region_name="us-east-1",
        wait_time_seconds=20,
        receive_batch_size=10,
        visibility_timeout=300,
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run-consumer --backend sqs --max-concurrency 4 --drain-timeout 60
```

`--max-concurrency` and `--drain-timeout` bound in-flight deliveries and
shutdown.

### Delivery Fencing

Every SQS delivery is fenced to the exact persisted retry generation and
dispatch attempt through a private message attribute, so a delivery that
outlives its record cannot execute a later attempt. `consume_one` accepts
`expected_retry_count` and `expected_execution_ref` to express the same fence
directly.

## Lost-Delivery Repair

On a queue nobody polls, a delivery that disappears would otherwise leave its
record waiting forever with no error raised. Bounded maintenance repairs
deliveries a managed transport has lost, sharing the existing external phase's
budget — so the number of records one pass touches is unchanged.

```bash
LITESTAR_APP=app:app litestar queues run-maintenance --json
```

## Observability

Managed transports report `litestar_queues.execution`,
`litestar_queues.execution.delivery`, and `litestar_queues.execution.repair`
metrics with a fixed outcome vocabulary. Task ids, delivery names, and API error
text never reach a metric, span, or event.

## Custom Backends

Queue backends must implement `clear_execution_ref` and `replace_execution_ref`,
and `claim_task` takes `expected_retry_count` and `expected_execution_ref`. The
shipped backends implement all of them. A custom backend only needs them to
serve an external transport, and raises rather than silently mis-settling a
record if it does not.

## Cross-References

- **[Namespacing](namespacing.md)** — running two queue runtimes in one process.
- **[litestar-deployment](../../litestar-deployment/SKILL.md)** — Cloud Run and container deployment.

## Official References

- <https://github.com/cofin/litestar-queues/blob/v0.8.0/docs/usage/deployment/sqs.rst>
- <https://github.com/cofin/litestar-queues/blob/v0.8.0/docs/usage/deployment/cloud-tasks.rst>
- <https://github.com/cofin/litestar-queues/tree/v0.8.0/src/litestar_queues/execution>
