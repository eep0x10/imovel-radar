"""One local command runs API + worker, shutting down both together."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
    from app.storage import initialize
    initialize()
    port = os.environ.get("IMOVEL_PORT", "8766")
    host = os.environ.get("IMOVEL_HOST", "127.0.0.1")
    processes = []
    try:
        processes.append(subprocess.Popen([sys.executable, "-m", "app.worker"]))
        processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", port, "--no-access-log"]))
        print(f"Imóvel Radar: http://{host}:{port}", flush=True)
        processes[-1].wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    return processes[-1].returncode if processes else 1


if __name__ == "__main__":
    sys.exit(main())
