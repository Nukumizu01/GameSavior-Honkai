import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workers.common import WorkerClient


class WorkerUpdatePauseTests(unittest.TestCase):
    def test_update_pause_is_false_without_control_directory(self):
        worker = WorkerClient.__new__(WorkerClient)
        worker.control_dir = None

        self.assertFalse(worker.update_pause_requested())

    def test_update_pause_tracks_marker_file(self):
        worker = WorkerClient.__new__(WorkerClient)
        with tempfile.TemporaryDirectory() as directory:
            worker.control_dir = Path(directory)
            self.assertFalse(worker.update_pause_requested())

            marker = Path(directory) / ".pause-for-march7th-update"
            marker.touch()
            self.assertTrue(worker.update_pause_requested())

    def test_register_advertises_update_pause_support(self):
        worker = WorkerClient.__new__(WorkerClient)
        worker.worker_key = "starrail-01"
        worker.name = "崩铁 Worker"
        worker.worker_type = "starrail"
        worker.command = "python main.py main"
        worker.control_dir = Path("/tmp/control")
        sent = {}
        worker._post = lambda path, payload: sent.update(path=path, payload=payload)

        worker.register()

        self.assertEqual(sent["path"], "/api/v1/worker/register")
        self.assertTrue(sent["payload"]["capabilities"]["pause_for_update"])

    def test_worker_does_not_claim_tasks_while_update_pause_is_requested(self):
        class StopLoop(BaseException):
            pass

        worker = WorkerClient.__new__(WorkerClient)
        worker.worker_key = "starrail-01"
        worker.poll_seconds = 10
        worker._monitor_login_qr = lambda: None
        worker.register = lambda: None
        worker.process_control_commands = lambda: None
        worker.heartbeat = lambda: None
        worker.update_pause_requested = lambda: True
        worker.next_job = lambda: self.fail("Worker claimed a task during update pause")

        with patch("workers.common.threading.Thread") as thread, patch(
            "workers.common.time.sleep", side_effect=StopLoop
        ):
            thread.return_value.start.return_value = None
            with self.assertRaises(StopLoop):
                worker.run_forever()


if __name__ == "__main__":
    unittest.main()
