# litestar-queues — Execution Backends Reference

An execution backend decides **where a claimed task runs**. It never owns queue state: arguments, task names, results, retries, schedules, and leases always stay in the queue backend.

| Backend | Worker process | Transport carries |
| --- | --- | --- |
| `"local"` | Yes, in-process pool | Nothing (direct call) |
| `"immediate"` | No — runs inline at enqueue | Nothing |
| `CloudRunExecutionConfig` | Per-task Cloud Run Job execution | Record id via env |
| `CloudTasksExecutionConfig` | None anywhere (serverless push) | Record id only |
| `KafkaExecutionConfig` | Continuous consumer fleet | Record id only |
| `PubSubExecutionConfig` | Continuous consumer fleet | Record id only |
| `RabbitMQExecutionConfig` | Continuous consumer fleet | Record id only |
| `SqsExecutionConfig` | Continuous consumer fleet | Record id only |

## Local and Immediate

`"local"` is the default: workers claim records and run them in-process, honoring `WorkerConfig.max_concurrency`, `WorkerConfig.queue_concurrency`, and the bounded sync thread pool.

`"immediate"` runs the task inline at enqueue time and is intended for tests and scripts. It requires `placement="external"`, because no worker owns the record.

## Google Cloud Run Jobs

Installed with `pip install "litestar-queues[cloudrun]"`.

```python
from litestar_queues import CloudRunExecutionConfig, QueueConfig

queue_config = QueueConfig(
    queue_backend="sqlspec",
    execution_backend=CloudRunExecutionConfig(
        project_id="example-project",
        region="us-central1",
        job_name="worker-job",
        profiles={
            "default": "worker-job",
            "heavy": "worker-job-heavy",
            "light": "worker-job-light",
        },
        timeout=900,
    ),
)
```

Each claimed record triggers an isolated Cloud Run Job execution. Use `profiles` for per-task resource shapes (`@task(..., execution_profile="heavy")`) and `fallback_execution_backend` to degrade to local execution when the API is unavailable. Calling `await queue_service.cancel_task(task_id, include_running=True)` cancels the active Cloud Run Job execution first before writing durable cancellation state.

## Google Cloud Tasks

Installed with `pip install "litestar-queues[cloud-tasks]"`.

A queue configured for Cloud Tasks keeps **no worker process anywhere**. Google holds each record's delivery and calls a private consumer route when it is due, so every process can scale to zero between deliveries. Only the record's id crosses the network; arguments, metadata, and results are re-read from the queue store by the consumer.

```python
from typing import Any, Literal

from litestar.connection import ASGIConnection
from litestar.exceptions import PermissionDeniedException
from litestar.handlers.base import BaseRouteHandler
from litestar_queues import CloudTasksExecutionConfig, QueueConfig, WorkerConfig
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig


def deny_cloud_tasks_delivery_guard(
    connection: ASGIConnection[Any, Any, Any, Any],
    _: BaseRouteHandler,
) -> None:
    raise PermissionDeniedException("Cloud Tasks delivery is disabled on this role")


def build_cloud_tasks_queue_config(
    sqlspec_config: Any,
    *,
    role: Literal["web", "consumer", "cli"] = "web",
) -> QueueConfig:
    is_consumer = role == "consumer"
    guards = () if is_consumer else (deny_cloud_tasks_delivery_guard,)
    return QueueConfig(
        queue_backend=SQLSpecBackendConfig(
            sqlspec_config=sqlspec_config,
            worker_wakeups=None,
        ),
        execution_backend=CloudTasksExecutionConfig(
            project_id="example-project",
            location="us-central1",
            queue_id="default",
            service_url="https://consumer.example.com",
            service_account_email="queues@example-project.iam.gserviceaccount.com",
            audience="https://consumer.example.com",
            dispatch_deadline=1800,
            response_margin=60.0,
            default_task_timeout=1680.0,
            trust_platform_auth=is_consumer,
            guards=guards,
        ),
        worker=WorkerConfig(placement="external"),
        initialize_schedules=False,
    )
```

The delivery route is registered at `/_litestar-queues/cloud-tasks` (or custom `route_path`) when the execution backend is Cloud Tasks. It requires **either** Cloud Run's own IAM asserted explicitly (`trust_platform_auth=True`) **or** application `guards`. It never treats a delivery header as authentication. In role-split deployments (`web` vs `consumer`), set `trust_platform_auth=False` and attach a deny guard on `web` instances so only the private `consumer` service accepts Cloud Tasks deliveries, and set `worker_wakeups=None` on `SQLSpecBackendConfig`.

When Cloud Tasks dispatch fails after the record was committed to SQL, `QueueService.enqueue()` raises `QueueDispatchError` with `exc.committed is True` and `exc.task_id` set so the caller can return a pending-dispatch status and let bounded maintenance repair delivery. Calling `await queue_service.cancel_task(task_id, include_running=True)` deletes the remote Cloud Task first before writing durable cancellation state.

## Apache Kafka

Installed with `pip install "litestar-queues[kafka]"`.

Run dispatchers alongside continuous consumers against the same persistent queue backend.

```python
from litestar_queues import KafkaExecutionConfig, QueueConfig

queue_config = QueueConfig(
    queue_backend="sqlspec",
    execution_backend=KafkaExecutionConfig(
        bootstrap_servers="localhost:9092",
        topic="litestar-queues",
        consumer_group="litestar-queues",
        dispatch_stale_after=60,
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run-consumer --backend kafka --max-concurrency 4 --drain-timeout 60
```

## Google Cloud Pub/Sub

Installed with `pip install "litestar-queues[pubsub]"`.

Dispatch task deliveries to a GCP Pub/Sub topic and consume them continuously via pull subscriptions.

```python
from litestar_queues import PubSubExecutionConfig, QueueConfig

queue_config = QueueConfig(
    queue_backend="sqlspec",
    execution_backend=PubSubExecutionConfig(
        project_id="example-project",
        topic_id="litestar-queues-tasks",
        subscription_id="litestar-queues-sub",
        ack_deadline=60,
        ack_extension_interval=30,
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run-consumer --backend pubsub --max-concurrency 4 --drain-timeout 60
```

## RabbitMQ

Installed with `pip install "litestar-queues[rabbitmq]"` (requires Python 3.11+ and `aio-pika>=10.0.1`).

Dispatch task deliveries to an AMQP queue and process them with continuous consumers.

```python
from litestar_queues import QueueConfig, RabbitMQExecutionConfig

queue_config = QueueConfig(
    queue_backend="sqlspec",
    execution_backend=RabbitMQExecutionConfig(
        amqp_url="amqp://guest:guest@localhost:5672/",
        queue_name="litestar-queues-tasks",
        declare_queue=True,
        delayed_retry_type="returned",
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run-consumer --backend rabbitmq --max-concurrency 4 --drain-timeout 60
```

## Amazon SQS

Installed with `pip install "litestar-queues[sqs]"`.

Run one dispatcher alongside any number of long-polling consumers against the same persistent queue backend. Standard queues are the default; `fifo=True` selects a FIFO queue.

```python
from litestar_queues import QueueConfig, SqsExecutionConfig

queue_config = QueueConfig(
    queue_backend="sqlspec",
    execution_backend=SqsExecutionConfig(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/tasks",
        region_name="us-east-1",
        wait_time_seconds=20,
        receive_batch_size=10,
        visibility_timeout=60,
        visibility_extension_interval=30,
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run-consumer --backend sqs --max-concurrency 4 --drain-timeout 60
```

`--max-concurrency` and `--drain-timeout` bound in-flight deliveries and shutdown.

### Delivery Fencing

Every broker delivery (SQS, Kafka, Pub/Sub, RabbitMQ) is fenced to the exact persisted retry generation and dispatch attempt through message attributes or metadata, so a delivery that outlives its record cannot execute a later attempt. `consume_one` accepts `expected_retry_count` and `expected_execution_ref` to express the same fence directly.

## Lost-Delivery Repair

On a queue nobody polls, a delivery that disappears would otherwise leave its record waiting forever with no error raised. Bounded maintenance (`QueueMaintenanceConfig(external_limit=100)`) repairs deliveries a managed transport has lost, sharing the external phase's budget. For Cloud Tasks, delivery repair selects unexpired pending and scheduled records (including records without delivery references), preserves task identity, and uses bounded fair selection tracked via `QueuedTaskRecord.dispatch_checked_at`.

```bash
LITESTAR_APP=app:app litestar queues run-maintenance --json
```

## Observability

Managed transports report `litestar_queues.execution`, `litestar_queues.execution.delivery`, and `litestar_queues.execution.repair` metrics with a fixed outcome vocabulary. Task ids, delivery names, and API error text never reach a metric, span, or event.

## Custom Backends

Queue backends must implement `clear_execution_ref` and `replace_execution_ref`, and `claim_task` takes `expected_retry_count` and `expected_execution_ref`. The shipped backends implement all of them. A custom backend only needs them to serve an external transport, and raises rather than silently mis-settling a record if it does not.

## Cross-References

- **[Namespacing](namespacing.md)** — running two queue runtimes in one process.
- **[litestar-deployment](../../litestar-deployment/SKILL.md)** — Cloud Run and container deployment.

## Official References

- <https://github.com/cofin/litestar-queues/blob/v0.12.0/docs/usage/deployment/sqs.rst>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/docs/usage/deployment/cloud-tasks.rst>
- <https://github.com/cofin/litestar-queues/tree/v0.12.0/src/litestar_queues/execution>
