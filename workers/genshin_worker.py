try:
    from .common import WorkerClient
except ImportError:
    from common import WorkerClient


if __name__ == "__main__":
    WorkerClient(
        worker_key="genshin-windows-01",
        worker_type="windows_genshin",
        name="Windows 原神 Worker",
        command_env="GENSHIN_COMMAND",
        workdir_env="GENSHIN_WORKDIR",
    ).run_forever()
