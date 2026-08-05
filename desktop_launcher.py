import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import ExitStack
from pathlib import Path


APP_NAME = "DurielMedicClinicServer"
BROWSER_HOST = "127.0.0.1"
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_PORT = 9000
PROJECT_ITEMS = [
    "DurielMedic",
    "DurielMedicApp",
    "DurielEyeApp",
    "DurielDentalApp",
    "core",
    "templates",
    "static",
    "staticfiles",
    "manage.py",
    "requirements.txt",
    "DESKTOP_VERSION",
]
RUNTIME_PRESERVE_NAMES = {
    ".env",
    "db.sqlite3",
    "logs",
    "media",
    ".migrated-version",
}


def bind_host() -> str:
    return os.getenv("DURIELMEDIC_BIND_HOST", DEFAULT_BIND_HOST)


def bind_port() -> int:
    try:
        return int(os.getenv("DURIELMEDIC_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


def browser_url() -> str:
    return f"http://{BROWSER_HOST}:{bind_port()}/"


def bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def shared_app_data_dir() -> Path:
    program_data = os.getenv("PROGRAMDATA")
    if program_data:
        return Path(program_data) / APP_NAME
    return Path.home() / APP_NAME


def runtime_dir() -> Path:
    configured_path = os.getenv("DURIELMEDIC_RUNTIME_DIR")
    if configured_path:
        return Path(configured_path)
    return shared_app_data_dir() / "runtime"


def launcher_log_path() -> Path:
    root = runtime_dir()
    try:
        (root / "logs").mkdir(parents=True, exist_ok=True)
        return root / "logs" / "launcher.log"
    except OSError:
        return Path(os.getenv("TEMP") or os.getcwd()) / "durielmedic-launcher.log"


def log_launcher(message: str) -> None:
    try:
        with launcher_log_path().open("a", encoding="utf-8") as log_file:
            log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def make_writable(path: Path) -> None:
    try:
        path.chmod(0o666)
    except OSError:
        pass


def copy_file_safely(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        make_writable(target)
    try:
        shutil.copy2(source, target)
    except PermissionError as exc:
        log_launcher(f"copy skipped permission-denied source={source} target={target} error={exc}")


def copy_tree_safely(source: Path, target: Path) -> None:
    for root, dir_names, file_names in os.walk(source):
        root_path = Path(root)
        ignored = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")(str(root_path), dir_names + file_names)
        relative_root = root_path.relative_to(source)
        target_root = target / relative_root
        target_root.mkdir(parents=True, exist_ok=True)

        for file_name in file_names:
            if file_name in ignored:
                continue
            copy_file_safely(root_path / file_name, target_root / file_name)


def read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def bundle_version(source_root: Path) -> str:
    return read_text_safely(source_root / "DESKTOP_VERSION")


def runtime_version(runtime_root: Path) -> str:
    return read_text_safely(runtime_root / "DESKTOP_VERSION")


def remove_path_safely(path: Path) -> None:
    if not path.exists():
        return
    try:
        if path.is_dir():
            shutil.rmtree(path, onerror=lambda func, item, exc_info: (make_writable(Path(item)), func(item)))
        else:
            make_writable(path)
            path.unlink()
    except OSError as exc:
        log_launcher(f"remove skipped path={path} error={exc}")


def refresh_runtime_for_new_version(source_root: Path, runtime_root: Path) -> bool:
    next_version = bundle_version(source_root)
    if not next_version or runtime_version(runtime_root) == next_version:
        return False

    log_launcher(f"runtime refresh start version={next_version}")
    for item_name in PROJECT_ITEMS:
        if item_name in RUNTIME_PRESERVE_NAMES:
            continue
        remove_path_safely(runtime_root / item_name)
    return True


def sync_project_files() -> Path:
    source_root = bundle_dir()
    runtime_root = runtime_dir()
    runtime_root.mkdir(parents=True, exist_ok=True)
    version_changed = refresh_runtime_for_new_version(source_root, runtime_root)

    # A frozen release is immutable. Copying thousands of unchanged files on
    # every launch delayed the browser and increased the chance of file locks.
    runtime_missing = not (runtime_root / "manage.py").exists()
    if version_changed or runtime_missing or not getattr(sys, "frozen", False):
        for item_name in PROJECT_ITEMS:
            source = source_root / item_name
            target = runtime_root / item_name
            if not source.exists():
                continue
            if source.is_dir():
                copy_tree_safely(source, target)
            else:
                copy_file_safely(source, target)

    ensure_env(runtime_root)
    (runtime_root / "logs").mkdir(exist_ok=True)
    (runtime_root / "media").mkdir(exist_ok=True)
    return runtime_root


def migrations_are_current(project_root: Path) -> bool:
    version = runtime_version(project_root)
    if not version:
        return False
    return read_text_safely(project_root / ".migrated-version") == version


def migrate_if_needed(project_root: Path) -> bool:
    if migrations_are_current(project_root):
        return True
    if run_management_command(project_root, ["migrate", "--noinput"]) != 0:
        return False
    version = runtime_version(project_root)
    if version:
        (project_root / ".migrated-version").write_text(version, encoding="utf-8")
    return True


def ensure_env(project_root: Path) -> None:
    env_path = project_root / ".env"
    if env_path.exists():
        return
    import secrets

    secret = secrets.token_urlsafe(64)
    env_path.write_text(
        "\n".join(
            [
                f"SECRET_KEY={secret}",
                "DEBUG=True",
                "ALLOWED_HOSTS=*",
                f"LOCAL_SERVER_PORT={bind_port()}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def runtime_env(project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DURIELMEDIC_DESKTOP"] = "1"
    env["DURIELMEDIC_RUNTIME_DIR"] = str(project_root)
    env["DURIELMEDIC_PORT"] = str(bind_port())
    env["DURIELMEDIC_SQLITE_PATH"] = str(project_root / "db.sqlite3")
    env["DEBUG"] = "True"
    env["DATABASE_URL"] = f"sqlite:///{project_root / 'db.sqlite3'}"
    env.setdefault("DJANGO_SETTINGS_MODULE", "DurielMedic.settings")
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def is_server_running() -> bool:
    try:
        with socket.create_connection((BROWSER_HOST, bind_port()), timeout=1):
            return True
    except OSError:
        return False


def wait_for_server(timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_server_running():
            return True
        time.sleep(0.25)
    return False


def execute_django_command(project_root: Path, command_args: list[str]) -> int:
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    os.environ.update(runtime_env(project_root))

    from django.core.management import execute_from_command_line

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    original_stdin = sys.stdin
    with ExitStack() as stack:
        if sys.stdout is None:
            sys.stdout = stack.enter_context((project_root / "logs" / "launcher.log").open("a", encoding="utf-8"))
        if sys.stderr is None:
            sys.stderr = stack.enter_context((project_root / "logs" / "launcher.log").open("a", encoding="utf-8"))
        if sys.stdin is None:
            sys.stdin = stack.enter_context(open(os.devnull, "r", encoding="utf-8"))
        try:
            execute_from_command_line(["manage.py", *command_args])
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            sys.stdin = original_stdin
    return 0


def run_management_command(project_root: Path, command: list[str]) -> int:
    if getattr(sys, "frozen", False):
        args = [sys.executable, "--manage", *command]
    else:
        args = [sys.executable, __file__, "--manage", *command]
    return subprocess.run(args, cwd=project_root, env=runtime_env(project_root), check=False).returncode


def server_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--serve"]
    return [sys.executable, __file__, "--serve"]


def sync_worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--manage", "sync_worker"]
    return [sys.executable, __file__, "--manage", "sync_worker"]


def launch_process(project_root: Path, command: list[str]) -> subprocess.Popen:
    log_file = (project_root / "logs" / "launcher.log").open("a", encoding="utf-8")
    return subprocess.Popen(
        command,
        cwd=project_root,
        env=runtime_env(project_root),
        stdout=log_file,
        stderr=log_file,
    )


def serve_mode() -> int:
    project_root = runtime_dir()
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    os.environ.update(runtime_env(project_root))
    from DurielMedic.wsgi import application

    try:
        from waitress import serve
    except ModuleNotFoundError:
        from wsgiref.simple_server import make_server

        with make_server(bind_host(), bind_port(), application) as server:
            server.serve_forever()
        return 0

    serve(application, host=bind_host(), port=bind_port())
    return 0


def manage_mode(arguments: list[str]) -> int:
    project_root = sync_project_files()
    return execute_django_command(project_root, arguments)


def activate_mode(activation_url: str) -> int:
    project_root = sync_project_files()
    if not migrate_if_needed(project_root):
        return 1
    return run_management_command(project_root, ["activate_local_clinic", activation_url])


def open_browser_once() -> None:
    webbrowser.open(browser_url(), new=1)


def main() -> int:
    if "--serve" in sys.argv:
        return serve_mode()
    if "--manage" in sys.argv:
        manage_index = sys.argv.index("--manage")
        return manage_mode(sys.argv[manage_index + 1 :])
    if "--activate" in sys.argv:
        activate_index = sys.argv.index("--activate")
        if len(sys.argv) <= activate_index + 1:
            print("Missing activation URL.")
            return 2
        return activate_mode(sys.argv[activate_index + 1])

    project_root = sync_project_files()
    if not migrate_if_needed(project_root):
        return 1

    if is_server_running():
        open_browser_once()
        return 0

    server = launch_process(project_root, server_command())
    sync_worker = None
    if wait_for_server():
        sync_worker = launch_process(project_root, sync_worker_command())
        open_browser_once()
        try:
            return server.wait()
        finally:
            if sync_worker and sync_worker.poll() is None:
                sync_worker.terminate()
                try:
                    sync_worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    sync_worker.kill()

    server.poll()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
