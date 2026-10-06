import os

try:
    from .common import WorkerClient
except ImportError:
    from common import WorkerClient


if __name__ == "__main__":
    WorkerClient(
        worker_key="starrail-01",
        worker_type="starrail",
        name="崩铁 Worker",
        command_env="STARRAIL_COMMAND",
        workdir_env="STARRAIL_WORKDIR",
        control_dir_env="STARRAIL_CONTROL_DIR",
        login_profile_dir_env="STARRAIL_LOGIN_PROFILE_DIR",
        login_qr_path_env="STARRAIL_LOGIN_QR_PATH",
        runtime_env={
            # March7thAssistant uses this supported marker for non-GUI/background runs.
            # The first GUI launch is still required to initialize and log in once.
            "MARCH7TH_DOCKER_STARTED": os.getenv("MARCH7TH_DOCKER_STARTED", "true"),
            "MARCH7TH_CLOUD_GAME_ENABLE": os.getenv("MARCH7TH_CLOUD_GAME_ENABLE", "true"),
            "MARCH7TH_BROWSER_HEADLESS_ENABLE": os.getenv("MARCH7TH_BROWSER_HEADLESS_ENABLE", "true"),
            "MARCH7TH_AFTER_FINISH": os.getenv("MARCH7TH_AFTER_FINISH", "Exit"),
            "MARCH7TH_LOG_LEVEL": os.getenv("MARCH7TH_LOG_LEVEL", "DEBUG"),
        },
    ).run_forever()
