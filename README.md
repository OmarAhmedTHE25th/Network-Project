# CSE361 — Computer Networks Major Task (Fall 2026)
### Project 2: RJDAP (Reliable Job Dispatch & Aggregation Protocol) — Phase 1



Team Members:
- Omar Ahmed Abdel Hameed (24P0201)
- Ahmed Mohamed Abd-Elmageed (2400136)
- Osama Ibrahim Ali (23P0323)
- Zyad Senousy (23P0139)
- Mohamed Amr Nady (24P0477)

Demo Video Link (5-Minute Walkthrough):
https://drive.google.com/file/d/1vj3QFIOKCD_ijq8Of1PhjH5vRLTmkXws/view?usp=sharing

--------------------------------------------------------------------------------
1. Prerequisites & Environment
--------------------------------------------------------------------------------
- Python 3.8+ (tested on Windows 10/11 and Linux/WSL2)
- Standard library only (socket, struct, zlib, subprocess, datetime) — no external
  packages or third-party networking libraries required.

--------------------------------------------------------------------------------
2. Repository Structure
--------------------------------------------------------------------------------
- protocol.py      : Binary wire framing, 18-byte big-endian header packing/unpacking,
                     and IEEE 802.3 CRC32 checksum validation.
- task_manager.py  : Server-side task queue lifecycle (PENDING -> IN_FLIGHT ->
                     COMPLETED) and duplicate result suppression.
- mock_server.py   : Phase 1 UDP server prototype supporting normal task dispatch
                     and network fault injection flags.
- worker.py        : UDP worker client with WORKER_JOIN handshake and stop-and-wait
                     ARQ retransmission (200ms timeout, max 5 attempts).
- run_baseline.py  : Automated Phase 1 local baseline test script (launches server
                     and worker, captures logs, and validates packet exchange).
- README.md        : Internal developer documentation for protocol.py and task_manager.py.

--------------------------------------------------------------------------------
3. How to Run Locally
--------------------------------------------------------------------------------
Option A — Automated Baseline Test (Recommended for Verification):
Run the automated baseline script from the project root directory:

    python run_baseline.py

What this does:
1. Launches mock_server.py on 127.0.0.1:5005.
2. Launches worker.py (worker_id=1) and initiates the WORKER_JOIN -> TASK_DISPATCH
   -> TASK_RESULT -> ACK_RESULT exchange over UDP.
3. Saves timestamped execution logs into the `logs/` directory:
   - logs/baseline_run_<YYYYMMDD_HHMMSS>.log
   - logs/worker_1.log
4. Verifies exit codes and required protocol events, printing:
   "FINAL RESULT: BASELINE TEST PASSED SUCCESSFULLY!"

Option B — Manual Two-Terminal Execution & Fault Simulation:
Terminal 1 (Start the Server):
    python mock_server.py

Optional fault-injection flags for testing reliability in Terminal 1:
    python mock_server.py --drop-first-ack    # Drops 1st ACK to verify worker retry
    python mock_server.py --wrong-ack-first   # Sends mismatched task_id ACK first
    python mock_server.py --never-ack         # Tests worker max retry limit (5)
    python mock_server.py --send-garbage      # Sends malformed bytes to test CRC/header check

Terminal 2 (Start the Worker):
    python worker.py [worker_id] [server_ip] [server_port]
    # Default: python worker.py 1 127.0.0.1 5005
