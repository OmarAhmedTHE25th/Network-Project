import subprocess
import sys
import time
import os
from datetime import datetime

SERVER_SCRIPT = "server.py"
WORKER_SCRIPT = "worker.py"
TIMEOUT_SECONDS = 10
LOG_DIR = "logs"

def verify_output(output_text, expected_keywords, role_name):
    missing = []
    output_lower = output_text.lower()
    
    for group in expected_keywords:
        if not any(keyword.lower() in output_lower for keyword in group):
            missing.append(" / ".join(group))
            
    if missing:
        print(f"[FAIL] {role_name} logs are missing expected indicators: {missing}")
        return False
    
    print(f"[PASS] {role_name} logs verified successfully.")
    return True

def run_baseline_test():
    print("=" * 60)
    print("Starting RJDAP Phase 1 - Baseline Local Automation Test")
    print("=" * 60)

    for script in [SERVER_SCRIPT, WORKER_SCRIPT]:
        if not os.path.exists(script):
            print(f"[ERROR] File '{script}' not found in the current directory!")
            sys.exit(1)

    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(LOG_DIR, f"baseline_run_{timestamp}.log")

    server_proc = None
    worker_proc = None

    try:
        print(f"[*] Launching {SERVER_SCRIPT} on 127.0.0.1:9999...")
        server_proc = subprocess.Popen(
            [sys.executable, "-u", SERVER_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        time.sleep(1.0)

        if server_proc.poll() is not None:
            _, s_err = server_proc.communicate()
            print(f"[ERROR] Server crashed immediately upon startup!\nError:\n{s_err}")
            sys.exit(1)

        print(f"[*] Launching {WORKER_SCRIPT}...")
        worker_proc = subprocess.Popen(
            [sys.executable, "-u", WORKER_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        print(f"[*] Waiting for packet exchange to complete (Timeout: {TIMEOUT_SECONDS}s)...")
        w_out, w_err = worker_proc.communicate(timeout=TIMEOUT_SECONDS)
        s_out, s_err = server_proc.communicate(timeout=TIMEOUT_SECONDS)

    except subprocess.TimeoutExpired:
        print(f"\n[FAIL] Test timed out after {TIMEOUT_SECONDS} seconds!")
        if worker_proc:
            worker_proc.kill()
        if server_proc:
            server_proc.kill()
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error occurred: {e}")
        if worker_proc:
            worker_proc.kill()
        if server_proc:
            server_proc.kill()
        sys.exit(1)

    print("\n" + "-" * 22 + " SERVER LOGS " + "-" * 25)
    print(s_out.strip() if s_out.strip() else "(No standard output from server)")
    if s_err.strip():
        print(f"[Server Stderr]:\n{s_err.strip()}")

    print("\n" + "-" * 22 + " WORKER LOGS " + "-" * 25)
    print(w_out.strip() if w_out.strip() else "(No standard output from worker)")
    if w_err.strip():
        print(f"[Worker Stderr]:\n{w_err.strip()}")
    print("-" * 60)

    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write(f"=== RJDAP Phase 1 Baseline Test ({timestamp}) ===\n\n")
        f.write("--- SERVER STDOUT ---\n" + s_out + "\n")
        f.write("--- SERVER STDERR ---\n" + s_err + "\n")
        f.write("--- WORKER STDOUT ---\n" + w_out + "\n")
        f.write("--- WORKER STDERR ---\n" + w_err + "\n")
    print(f"[*] Raw logs saved to: {log_file_path}")

    print("\n[*] Validating Execution & Logs...")

    exit_codes_ok = (server_proc.returncode == 0) and (worker_proc.returncode == 0)
    if not exit_codes_ok:
        print(f"[FAIL] Non-zero exit code detected! (Server: {server_proc.returncode}, Worker: {worker_proc.returncode})")
    else:
        print("[PASS] Both Server and Worker exited cleanly (Return Code 0).")

    expected_server_logs = [
        ["worker_join", "join", "connected", "worker"],
        ["task_result", "result", "done", "received", "ack_result"]
    ]

    expected_worker_logs = [
        ["task_dispatch", "task", "dispatch", "received"],
        ["ack_result", "ack", "completed", "finished", "done"]
    ]

    server_logs_ok = verify_output(s_out, expected_server_logs, "Server")
    worker_logs_ok = verify_output(w_out, expected_worker_logs, "Worker")

    print("=" * 60)
    if exit_codes_ok and server_logs_ok and worker_logs_ok:
        print("FINAL RESULT: BASELINE TEST PASSED SUCCESSFULLY!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("FINAL RESULT: BASELINE TEST FAILED! CHECK LOGS ABOVE.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    run_baseline_test()