"""ARQ worker entrypoint (V2 R2-1). Run with: arq app.workers.main.WorkerSettings

`functions` and `cron_jobs` are registries other V2 tasks append to as they
land (R2-2's import-batch email job, later phases' scheduled jobs) — don't
replace these lists, extend them.
"""

from arq import cron

from app.workers.heartbeat import heartbeat
from app.workers.settings import redis_settings
from app.workers.tasks.imports import send_import_batch_emails
from app.workers.tasks.staffing import send_assignment_email
from app.workers.tasks.tickets import send_ticket_email


class WorkerSettings:
    redis_settings = redis_settings()
    functions = [send_ticket_email, send_import_batch_emails, send_assignment_email]
    cron_jobs = [cron(heartbeat, minute=set(range(0, 60, 5)), run_at_startup=True)]
