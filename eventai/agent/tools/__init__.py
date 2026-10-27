"""Part 2 tools. Each external call has a timeout and retries with backoff; a final failure raises
ToolError, and the run flags the affected records instead of stopping (CLAUDE.md 10.4)."""

from collections.abc import Callable

from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

TIMEOUT_SECONDS = 10
ATTEMPTS = 3
# Module level, so the tests can set wait_none().
WAIT = wait_exponential(multiplier=0.5, max=4)


class ToolError(RuntimeError):
    """A tool call failed after its retries."""


def retrying(retryable: Callable[[BaseException], bool]) -> Retrying:
    return Retrying(stop=stop_after_attempt(ATTEMPTS), wait=WAIT, retry=retry_if_exception(retryable), reraise=True)
