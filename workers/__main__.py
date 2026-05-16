"""Allow running workers via python -m workers.run_worker."""

from workers.run_worker import WorkerSettings

if __name__ == "__main__":
    import arq.worker

    arq.worker.run_worker(WorkerSettings)  # type: ignore[arg-type]
