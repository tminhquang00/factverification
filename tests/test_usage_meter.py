import threading
import unittest

from llm_client import UsageMeter


class _Usage:
    def __init__(self, prompt_tokens=None, completion_tokens=None, total_tokens=None):
        if prompt_tokens is not None:
            self.prompt_tokens = prompt_tokens
        if completion_tokens is not None:
            self.completion_tokens = completion_tokens
        if total_tokens is not None:
            self.total_tokens = total_tokens


class UsageMeterTotalsTests(unittest.TestCase):
    def test_totals_accumulate_across_calls(self):
        meter = UsageMeter()
        meter.record(0.4, _Usage(10, 5, 15))
        meter.record(0.6, _Usage(20, 10, 30))

        snapshot = meter.snapshot()
        self.assertEqual(snapshot["n_calls"], 2)
        self.assertEqual(snapshot["prompt_tokens"], 30)
        self.assertEqual(snapshot["completion_tokens"], 15)
        self.assertEqual(snapshot["total_tokens"], 45)
        self.assertTrue(snapshot["tokens_complete"])
        self.assertAlmostEqual(snapshot["latency_s"]["sum"], 1.0)
        self.assertAlmostEqual(snapshot["latency_s"]["mean"], 0.5)

    def test_total_is_derived_when_the_provider_omits_it(self):
        meter = UsageMeter()
        meter.record(0.1, _Usage(prompt_tokens=7, completion_tokens=3))

        self.assertEqual(meter.snapshot()["total_tokens"], 10)

    def test_calls_with_no_usage_block_are_counted_not_silently_zeroed(self):
        """A local server that omits `usage` must not make a partial token total look complete."""
        meter = UsageMeter()
        meter.record(0.2, _Usage(10, 5, 15))
        meter.record(0.2, None)

        snapshot = meter.snapshot()
        self.assertEqual(snapshot["n_calls"], 2)
        self.assertEqual(snapshot["n_calls_without_usage"], 1)
        self.assertEqual(snapshot["total_tokens"], 15)
        self.assertFalse(snapshot["tokens_complete"])

    def test_failed_calls_are_timed_and_counted(self):
        meter = UsageMeter()
        meter.record(1.5, None, failed=True)

        snapshot = meter.snapshot()
        self.assertEqual(snapshot["n_calls"], 1)
        self.assertEqual(snapshot["n_failed_calls"], 1)
        self.assertAlmostEqual(snapshot["latency_s"]["max"], 1.5)

    def test_empty_meter_reports_no_latency_rather_than_zero(self):
        snapshot = UsageMeter().snapshot()
        self.assertEqual(snapshot["n_calls"], 0)
        self.assertIsNone(snapshot["latency_s"]["mean"])
        self.assertIsNone(snapshot["latency_s"]["p95"])


class UsageMeterScopeTests(unittest.TestCase):
    """Per-row attribution has to survive a thread pool that reuses worker threads."""

    def test_scope_captures_only_its_own_calls(self):
        meter = UsageMeter()
        meter.record(0.1, _Usage(1, 1, 2))  # outside any scope

        with meter.scope() as row:
            meter.record(0.2, _Usage(10, 5, 15))
            meter.record(0.3, _Usage(20, 10, 30))

        self.assertEqual(row["n_calls"], 2)
        self.assertEqual(row["total_tokens"], 45)
        self.assertAlmostEqual(row["latency_s_sum"], 0.5)
        # Global totals still include every call, scoped or not.
        self.assertEqual(meter.snapshot()["n_calls"], 3)
        self.assertEqual(meter.snapshot()["total_tokens"], 47)

    def test_consecutive_scopes_on_one_thread_do_not_leak(self):
        """ThreadPoolExecutor reuses threads, so a stale bucket would double-count rows."""
        meter = UsageMeter()

        with meter.scope() as first:
            meter.record(0.1, _Usage(10, 0, 10))
        with meter.scope() as second:
            meter.record(0.1, _Usage(20, 0, 20))

        self.assertEqual(first["total_tokens"], 10)
        self.assertEqual(second["total_tokens"], 20)

    def test_concurrent_scopes_are_attributed_per_thread(self):
        meter = UsageMeter()
        buckets = {}
        started = threading.Barrier(4)

        def worker(n):
            started.wait()
            with meter.scope() as row:
                for _ in range(n):
                    meter.record(0.01, _Usage(1, 1, 2))
            buckets[n] = row

        threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2, 3, 4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for n in (1, 2, 3, 4):
            self.assertEqual(buckets[n]["n_calls"], n, f"thread {n} saw another thread's calls")
            self.assertEqual(buckets[n]["total_tokens"], 2 * n)
        self.assertEqual(meter.snapshot()["n_calls"], 10)
        self.assertEqual(meter.snapshot()["total_tokens"], 20)

    def test_scope_records_failures_for_the_row(self):
        meter = UsageMeter()
        with meter.scope() as row:
            meter.record(0.5, None, failed=True)

        self.assertEqual(row["n_failed_calls"], 1)
        self.assertEqual(row["n_calls_without_usage"], 1)


if __name__ == "__main__":
    unittest.main()
