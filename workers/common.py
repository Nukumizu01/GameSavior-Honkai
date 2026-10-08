from __future__ import annotations

import os
import json
import queue
import signal
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(
    os.getenv("WORKER_ENV_FILE", str(PROJECT_ROOT / ".env")),
    override=False,
)


SAFE_CONFIG_KEYS = {
    "power_enable", "instance_type", "instance_name", "tp_before_instance", "use_reserved_trailblaze_power",
    "use_fuel", "merge_immersifier", "build_target_enable", "build_target_scheme",
    "echo_of_war_enable", "borrow_enable", "borrow_character_enable", "borrow_scroll_times",
    "daily_enable", "daily_material_enable", "daily_himeko_try_enable", "daily_memory_one_enable",
    "reward_enable", "reward_dispatch_enable", "reward_mail_enable", "reward_assist_enable",
    "reward_quest_enable", "reward_srpass_enable", "reward_redemption_code_enable",
    "reward_achievement_enable", "reward_message_enable", "activity_enable",
    "activity_dailycheckin_enable", "activity_gardenofplenty_enable",
    "activity_realmofthestrange_enable", "activity_planarfissure_enable",
    "currencywars_enable", "currencywars_type", "currencywars_rank_difficulty",
    "currencywars_bonus_enable", "currencywars_fast_mode", "currencywars_strategy",
    "currencywars_remembrance_trailblazer_name", "currencywars_strategy_restart_on_special_tags",
    "weekly_divergent_enable", "weekly_divergent_type", "weekly_divergent_level",
    "weekly_divergent_bonus_enable", "weekly_divergent_stable_mode", "universe_enable",
    "universe_category", "universe_frequency", "universe_count", "universe_timeout",
    "universe_difficulty", "fight_enable", "fight_timeout", "fight_team_enable",
    "fight_map_version", "fight_main_map", "cloud_game_enable", "cloud_game_fullscreen_enable",
    "cloud_game_use_paid_time", "cloud_game_max_queue_time", "cloud_game_login_timeout",
    "browser_type", "browser_headless_enable", "browser_headless_restart_on_not_logged_in",
    "browser_persistent_enable", "browser_download_use_mirror", "browser_scale_factor",
    "log_level", "pause_after_success", "exit_after_failure", "after_finish", "loop_mode",
    "power_limit", "refresh_hour", "play_audio", "notification_enable", "notify_level",
    "notify_merge", "notify_send_images", "auto_battle_detect_enable", "ocr_gpu_acceleration",
    "auto_set_resolution_enable", "auto_set_game_path_enable", "use_background_screenshot",
}

INSTANCE_NAME_CONFIG_KEYS = {
    "instance_name_calyx_golden": "拟造花萼（金）",
    "instance_name_calyx_crimson": "拟造花萼（赤）",
    "instance_name_stagnant_shadow": "凝滞虚影",
    "instance_name_cavern": "侵蚀隧洞",
    "instance_name_ornament": "饰品提取",
    "instance_name_echo_of_war": "历战余响",
}


class WorkerClient:
    SCRIPT_FAILURE_MARKERS = (
        "每日实训未完成",
        "清体力未完成",
        "任务无法完成",
        "等待云游戏登录超时",
        "任务执行失败",
        "发生错误",
    )

    def __init__(
        self,
        worker_key: str,
        worker_type: str,
        name: str,
        command_env: str,
        workdir_env: str,
        control_dir_env: str | None = None,
        login_profile_dir_env: str | None = None,
        login_qr_path_env: str | None = None,
        runtime_env: dict[str, str] | None = None,
    ):
        self.base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
        self.token = os.getenv("WORKER_TOKEN", "change-worker-token-now")
        self.worker_key = worker_key
        self.worker_type = worker_type
        self.name = name
        self.command = os.getenv(command_env, "")
        self.workdir = Path(os.getenv(workdir_env, "")).expanduser() if os.getenv(workdir_env) else None
        self.control_dir = (
            Path(os.getenv(control_dir_env, "")).expanduser()
            if control_dir_env and os.getenv(control_dir_env)
            else None
        )
        self.login_profile_dir = (
            Path(os.getenv(login_profile_dir_env, "")).expanduser()
            if login_profile_dir_env and os.getenv(login_profile_dir_env)
            else None
        )
        self.login_qr_path = (
            Path(os.getenv(login_qr_path_env, "")).expanduser()
            if login_qr_path_env and os.getenv(login_qr_path_env)
            else None
        )
        self.config_source_path = (
            Path(os.getenv("STARRAIL_CONFIG_SOURCE_PATH", "")).expanduser()
            if os.getenv("STARRAIL_CONFIG_SOURCE_PATH")
            else None
        )
        self.runtime_env = runtime_env or {}
        self.poll_seconds = int(os.getenv("WORKER_POLL_SECONDS", "10"))
        self.log_dir = Path(os.getenv("WORKER_LOG_DIR", "./worker_logs"))
        self.login_qr_signature: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Worker-Token": self.token}

    def register(self) -> None:
        self._post(
            "/api/v1/worker/register",
            {
                "worker_key": self.worker_key,
                "name": self.name,
                "worker_type": self.worker_type,
                "version": "0.1.0",
                "capabilities": {"command_configured": bool(self.command)},
            },
        )

    def heartbeat(self, current_run_id: int | None = None) -> None:
        self._post(
            "/api/v1/worker/heartbeat",
            {"worker_key": self.worker_key, "status": "online", "current_run_id": current_run_id},
        )

    def next_job(self) -> dict[str, Any] | None:
        resp = requests.get(
            f"{self.base_url}/api/v1/worker/jobs/next",
            headers=self.headers,
            params={"worker_key": self.worker_key},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("job")

    def event(self, run_id: int, event_type: str, message: str, level: str = "info", **extra: Any) -> None:
        payload = {"level": level, "event_type": event_type, "message": message, **extra}
        self._post(f"/api/v1/worker/runs/{run_id}/events", payload)

    def finish(self, run_id: int, status: str, **extra: Any) -> None:
        payload = {"status": status, **extra}
        self._post(f"/api/v1/worker/runs/{run_id}/finish", payload)

    def is_run_cancelled(self, run_id: int) -> bool:
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/worker/runs/{run_id}/control",
                headers=self.headers,
                timeout=3,
            )
            response.raise_for_status()
            return bool(response.json().get("cancelled"))
        except requests.RequestException as exc:
            print(f"[worker] cancellation check failed: {exc}")
            return False

    def upload(self, run_id: int, path: Path, kind: str) -> None:
        with path.open("rb") as fh:
            resp = requests.post(
                f"{self.base_url}/api/v1/worker/runs/{run_id}/artifacts",
                headers=self.headers,
                data={"kind": kind},
                files={"file": (path.name, fh, "application/octet-stream")},
                timeout=60,
            )
        resp.raise_for_status()

    def upload_recent_screenshots(self, run_id: int, started_at: float) -> None:
        if not self.workdir:
            return
        screenshot_dir = self.workdir / "logs" / "screenshots"
        if not screenshot_dir.is_dir():
            return
        for path in sorted(screenshot_dir.rglob("*")):
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            try:
                if path.stat().st_mtime < started_at - 2:
                    continue
                self.upload(run_id, path, "screenshot")
            except Exception as exc:
                self.event(
                    run_id,
                    "warning",
                    f"Screenshot upload failed: {exc}",
                    level="warning",
                    code="SCREENSHOT_UPLOAD_FAILED",
                )

    def _write_login_switch_status(self, payload: dict[str, Any]) -> None:
        if not self.control_dir:
            return
        self.control_dir.mkdir(parents=True, exist_ok=True)
        status_path = self.control_dir / "switch_login.status.json"
        temporary_path = self.control_dir / f".{status_path.name}.tmp"
        try:
            temporary_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary_path.replace(status_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _cleanup_temporary_files(directory: Path) -> None:
        if not directory.is_dir():
            return
        for path in directory.glob(".*.tmp"):
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
            except OSError as exc:
                print(f"[worker] temporary file cleanup failed for {path}: {exc}")

    def _clear_login_profile(self) -> int:
        if not self.login_profile_dir:
            return 0
        self.login_profile_dir.mkdir(parents=True, exist_ok=True)
        deleted = 0
        for child in self.login_profile_dir.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
            deleted += 1
        return deleted

    def apply_script_config(self, script_settings: dict[str, Any]) -> None:
        if not self.workdir:
            return
        config_path = self.workdir / "config.yaml"
        if not config_path.is_file():
            print(f"[worker] script config not found: {config_path}")
            return

        overrides = {
            "cloud_game_enable": script_settings.get("cloud_game_enabled", True),
            "browser_headless_enable": script_settings.get("browser_headless_enabled", True),
            "browser_headless_restart_on_not_logged_in": script_settings.get(
                "browser_headless_restart_on_not_logged_in",
                False,
            ),
            "after_finish": script_settings.get("after_finish", "Exit"),
            "log_level": script_settings.get("log_level", "DEBUG"),
        }
        custom_overrides = script_settings.get("config_overrides", {})
        instance_name_overrides: dict[str, str] = {}
        if isinstance(custom_overrides, dict):
            for key, value in custom_overrides.items():
                if str(key) in SAFE_CONFIG_KEYS and isinstance(value, (bool, int, float, str)):
                    overrides[str(key)] = value
                elif str(key) in INSTANCE_NAME_CONFIG_KEYS and isinstance(value, str):
                    instance_name_overrides[INSTANCE_NAME_CONFIG_KEYS[str(key)]] = value

        try:
            document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if not isinstance(document, dict):
                raise ValueError("config.yaml root must be a mapping")
            changed = set()
            for key, value in overrides.items():
                if document.get(key) != value:
                    document[key] = value
                    changed.add(key)
            if instance_name_overrides:
                instance_names = document.setdefault("instance_names", {})
                if not isinstance(instance_names, dict):
                    instance_names = {}
                    document["instance_names"] = instance_names
                for instance_type, instance_name in instance_name_overrides.items():
                    if instance_names.get(instance_type) != instance_name:
                        instance_names[instance_type] = instance_name
                        changed.add(f"instance_names.{instance_type}")
            if changed:
                backup_path = config_path.with_suffix(".yaml.bak")
                if not backup_path.exists():
                    shutil.copy2(config_path, backup_path)
                temporary_path = config_path.with_suffix(".yaml.tmp")
                temporary_path.write_text(
                    yaml.safe_dump(
                        document,
                        allow_unicode=True,
                        sort_keys=False,
                        default_flow_style=False,
                    ),
                    encoding="utf-8",
                )
                try:
                    temporary_path.replace(config_path)
                except OSError as replace_error:
                    # A single-file Docker bind mount cannot be atomically replaced.
                    # Fall back to writing the mounted file in place so UI settings
                    # still reach March7thAssistant.
                    config_path.write_text(temporary_path.read_text(encoding="utf-8"), encoding="utf-8")
                    temporary_path.unlink(missing_ok=True)
                    print(f"[worker] atomic config replace unavailable; wrote in place: {replace_error}")
                finally:
                    temporary_path.unlink(missing_ok=True)
            print(f"[worker] updated script config: {', '.join(sorted(changed))}")
        except Exception as exc:
            print(f"[worker] script config update failed: {exc}")

    def _sync_config_from_source(self) -> None:
        """Copy the host-persisted config into a regular container file.

        A single-file Docker bind mount cannot be replaced with os.replace;
        March7thAssistant saves config.yaml during normal tasks.  Keeping the
        working copy inside the container lets that save remain atomic.
        """
        if not self.config_source_path or not self.workdir:
            return
        target = self.workdir / "config.yaml"
        try:
            if self.config_source_path.is_file():
                shutil.copy2(self.config_source_path, target)
            elif target.is_file():
                self.config_source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, self.config_source_path)
        except OSError as exc:
            print(f"[worker] config sync from source failed: {exc}")

    def _sync_config_to_source(self) -> None:
        if not self.config_source_path or not self.workdir:
            return
        target = self.workdir / "config.yaml"
        if not target.is_file():
            return
        try:
            self.config_source_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, self.config_source_path)
        except OSError as exc:
            print(f"[worker] config sync to source failed: {exc}")

    def process_control_commands(self) -> None:
        if not self.control_dir:
            return
        self._cleanup_temporary_files(self.control_dir)
        request_path = self.control_dir / "switch_login.json"
        if not request_path.is_file():
            return

        request: dict[str, Any] = {}
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
            if request.get("action") != "switch_login":
                raise ValueError("Unsupported control action")
            deleted_entries = self._clear_login_profile()
            if self.login_qr_path and self.login_qr_path.exists():
                self.login_qr_path.unlink()
            self._write_login_switch_status(
                {
                    "status": "ready_for_scan",
                    "request_id": request.get("request_id"),
                    "requested_at": request.get("requested_at"),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "deleted_profile_entries": deleted_entries,
                }
            )
            print(f"[worker] login switch completed; cleared {deleted_entries} profile entries")
        except Exception as exc:
            self._write_login_switch_status(
                {
                    "status": "error",
                    "request_id": request.get("request_id"),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                }
            )
            print(f"[worker] login switch failed: {exc}")
        finally:
            request_path.unlink(missing_ok=True)

    def process_login_qr(self) -> None:
        if not self.control_dir or not self.login_qr_path or not self.login_qr_path.is_file():
            return
        status_path = self.control_dir / "switch_login.status.json"
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}

        qr_stat = self.login_qr_path.stat()
        signature = f"{qr_stat.st_mtime_ns}:{qr_stat.st_size}"
        if status.get("qr_sent_signature") == signature:
            return
        if self.login_qr_signature == signature:
            return
        last_attempt = status.get("qr_last_attempt_at")
        if last_attempt:
            try:
                if (datetime.now(timezone.utc) - datetime.fromisoformat(last_attempt)).total_seconds() < 60:
                    return
            except ValueError:
                pass
        self.login_qr_signature = signature

        try:
            with self.login_qr_path.open("rb") as fh:
                response = requests.post(
                    f"{self.base_url}/api/v1/worker/starrail/login-qr",
                    headers=self.headers,
                    files={"file": (self.login_qr_path.name, fh, "image/png")},
                    timeout=60,
                )
            response.raise_for_status()
            result = response.json()
            status["qr_last_attempt_at"] = datetime.now(timezone.utc).isoformat()
            status["qr_notification_status"] = "sent" if result.get("ok") else "failed"
            if result.get("ok"):
                status["qr_sent_signature"] = signature
                status["qr_sent_at"] = status["qr_last_attempt_at"]
            else:
                status["qr_notification_error"] = "API returned ok=false"
        except Exception as exc:
            status["qr_last_attempt_at"] = datetime.now(timezone.utc).isoformat()
            status["qr_notification_status"] = "failed"
            status["qr_notification_error"] = str(exc)
        finally:
            self._write_login_switch_status(status)
            self.login_qr_signature = None

    @staticmethod
    def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                )
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    @staticmethod
    def _read_process_output(stream, output_queue: queue.Queue[str | None]) -> None:
        try:
            for line in iter(stream.readline, ""):
                output_queue.put(line)
        finally:
            output_queue.put(None)

    def _analyze_script_result(self, log_path: Path) -> dict[str, Any]:
        """Convert script-level 'unfinished' output into a failed Worker result."""
        if not log_path.is_file():
            return {}

        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {
                "log_read_error": str(exc),
            }

        matched: list[dict[str, str]] = []
        for line in text.splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue
            for marker in self.SCRIPT_FAILURE_MARKERS:
                if marker in clean_line:
                    matched.append({"marker": marker, "line": clean_line[-1000:]})
                    break

        if not matched:
            return {}
        return {
            "script_result": "incomplete",
            "detected_failures": matched,
        }

    def execute_job(self, run_id: int, job: dict[str, Any] | None = None) -> None:
        self.event(run_id, "run_started", f"{self.name} started")
        if not self.command:
            self.event(
                run_id,
                "error",
                f"No command configured for {self.name}; real script was not started",
                level="error",
                code="SCRIPT_COMMAND_NOT_CONFIGURED",
            )
            self.finish(
                run_id,
                "failed",
                error_code="SCRIPT_COMMAND_NOT_CONFIGURED",
                error_message=f"{self.name} command is empty",
                summary={"mode": "not_configured"},
            )
            return

        if self.workdir and not self.workdir.exists():
            self.event(
                run_id,
                "error",
                f"Script working directory does not exist: {self.workdir}",
                level="error",
                code="SCRIPT_WORKDIR_NOT_FOUND",
            )
            self.finish(
                run_id,
                "failed",
                error_code="SCRIPT_WORKDIR_NOT_FOUND",
                error_message=str(self.workdir),
                summary={"command": self.command},
            )
            return

        if self.is_run_cancelled(run_id):
            self.finish(
                run_id,
                "cancelled",
                error_code="TASK_CANCELLED",
                error_message="Cancellation requested before script start",
                summary={"mode": "cancelled_before_start"},
            )
            return

        self._sync_config_from_source()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"{self.worker_key}-{run_id}.log"
        env = os.environ.copy()
        env.update(self.runtime_env)
        env.setdefault("PYTHONUNBUFFERED", "1")
        task = (job or {}).get("task") or {}
        try:
            snapshot = json.loads(task.get("config_snapshot_json", "{}"))
            stored_options = json.loads(snapshot.get("task_options_json", "{}"))
            if not isinstance(stored_options, dict):
                stored_options = {}
            script_settings = stored_options.get("_script", {})
            custom_task_options = stored_options.get("custom", stored_options)
            manual_options = snapshot.get("manual_options", {})
            task_options = {
                **(custom_task_options if isinstance(custom_task_options, dict) else {}),
                **(manual_options if isinstance(manual_options, dict) else {}),
            }
        except (TypeError, json.JSONDecodeError):
            snapshot = {}
            script_settings = {}
            task_options = {}
        if not isinstance(script_settings, dict):
            script_settings = {}
        self.apply_script_config(script_settings)
        env["GAME_AUTOMATION_TASK_ID"] = str(task.get("id", ""))
        env["GAME_AUTOMATION_RUN_ID"] = str(run_id)
        env["GAME_AUTOMATION_OPTIONS_JSON"] = json.dumps(task_options, ensure_ascii=False)
        env["MARCH7TH_CLOUD_GAME_ENABLE"] = str(
            script_settings.get("cloud_game_enabled", env.get("MARCH7TH_CLOUD_GAME_ENABLE", "true"))
        ).lower()
        env["MARCH7TH_BROWSER_HEADLESS_ENABLE"] = str(
            script_settings.get(
                "browser_headless_enabled",
                env.get("MARCH7TH_BROWSER_HEADLESS_ENABLE", "true"),
            )
        ).lower()
        env["MARCH7TH_BROWSER_HEADLESS_RESTART_ON_NOT_LOGGED_IN"] = str(
            script_settings.get(
                "browser_headless_restart_on_not_logged_in",
                env.get("MARCH7TH_BROWSER_HEADLESS_RESTART_ON_NOT_LOGGED_IN", "false"),
            )
        ).lower()
        env["MARCH7TH_AFTER_FINISH"] = str(
            script_settings.get("after_finish", env.get("MARCH7TH_AFTER_FINISH", "Exit"))
        )
        env["MARCH7TH_LOG_LEVEL"] = str(
            script_settings.get("log_level", env.get("MARCH7TH_LOG_LEVEL", "DEBUG"))
        )
        self.event(
            run_id,
            "stage_started",
            f"Starting configured script: {self.command}",
            stage="script_start",
            payload={
                "workdir": str(self.workdir) if self.workdir else None,
                "task_options": task_options,
            },
        )

        returncode = None
        cancelled = False
        started_at = time.monotonic()
        wall_started_at = time.time()
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
                popen_kwargs: dict[str, Any] = {}
                if os.name == "nt":
                    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    popen_kwargs["start_new_session"] = True
                proc = subprocess.Popen(
                    self.command,
                    cwd=str(self.workdir) if self.workdir else None,
                    env=env,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **popen_kwargs,
                )
                assert proc.stdout is not None
                output_queue: queue.Queue[str | None] = queue.Queue()
                reader = threading.Thread(
                    target=self._read_process_output,
                    args=(proc.stdout, output_queue),
                    daemon=True,
                )
                reader.start()
                stream_closed = False
                while not stream_closed or proc.poll() is None or not output_queue.empty():
                    if not cancelled and self.is_run_cancelled(run_id):
                        cancelled = True
                        self.event(
                            run_id,
                            "warning",
                            "Cancellation received; terminating the script process tree.",
                            level="warning",
                            code="TASK_CANCELLED",
                        )
                        self._terminate_process_tree(proc)
                    try:
                        line = output_queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    if line is None:
                        stream_closed = True
                        continue
                    clean_line = line.rstrip()
                    if clean_line:
                        log_file.write(clean_line + "\n")
                        log_file.flush()
                        self.event(run_id, "log", clean_line[-4000:], stage="script_output")
                returncode = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if "proc" in locals():
                self._terminate_process_tree(proc)
            self.event(run_id, "error", "Configured script did not exit after output stream closed", level="error", code="SCRIPT_SHUTDOWN_TIMEOUT")
            returncode = -9
        except Exception as exc:
            if "proc" in locals():
                self._terminate_process_tree(proc)
            self.event(run_id, "error", str(exc), level="error", code="SCRIPT_EXECUTION_ERROR")
            returncode = -1

        if log_path.exists():
            try:
                self.upload(run_id, log_path, "worker_log")
            except Exception as exc:
                self.event(run_id, "warning", f"Log upload failed: {exc}", level="warning", code="LOG_UPLOAD_FAILED")
        self.upload_recent_screenshots(run_id, wall_started_at)

        duration_ms = int((time.monotonic() - started_at) * 1000)
        script_result = self._analyze_script_result(log_path)
        self._sync_config_to_source()
        if cancelled:
            self.finish(
                run_id,
                "cancelled",
                error_code="TASK_CANCELLED",
                error_message="Cancellation requested by user",
                summary={"returncode": returncode, "duration_ms": duration_ms, **script_result},
            )
        elif script_result.get("detected_failures"):
            first_failure = script_result["detected_failures"][0]
            self.event(
                run_id,
                "error",
                f"Script reported an incomplete task: {first_failure['line']}",
                level="error",
                code="SCRIPT_INCOMPLETE",
                payload=script_result,
            )
            self.finish(
                run_id,
                "failed",
                error_code="SCRIPT_INCOMPLETE",
                error_message=first_failure["line"],
                summary={"returncode": returncode, "duration_ms": duration_ms, **script_result},
            )
        elif returncode == 0:
            self.finish(
                run_id,
                "succeeded",
                summary={"returncode": returncode, "duration_ms": duration_ms, **script_result},
            )
        else:
            self.finish(
                run_id,
                "failed",
                error_code="COMMAND_FAILED",
                error_message=f"Command exited with {returncode}",
                summary={"returncode": returncode, "duration_ms": duration_ms, **script_result},
            )

    def run_forever(self) -> None:
        registered = False
        retry_delay = 1
        while True:
            try:
                if not registered:
                    self.register()
                    registered = True
                    retry_delay = 1
                    print(f"[worker] registered as {self.worker_key}")
                self.process_control_commands()
                self.process_login_qr()
                self.heartbeat()
                job = self.next_job()
                if job:
                    run_id = int(job["run_id"])
                    self.heartbeat(run_id)
                    self.execute_job(run_id, job)
            except requests.RequestException as exc:
                registered = False
                print(f"[worker] API unavailable; retrying in {retry_delay}s: {exc}")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
            except Exception as exc:
                print(f"[worker] {exc}")
            if registered:
                time.sleep(self.poll_seconds)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = requests.post(f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
