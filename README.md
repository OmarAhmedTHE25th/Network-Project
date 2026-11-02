# Protocol Internals (`protocol.py`)

This is the implementation of the RJDAP protocol. It handles all the byte-level stuff—packing, unpacking, CRC checks, and header formatting over raw UDP.

**Note:** You shouldn't need to mess with bitwise ops or structs. Just use `pack_message` and `unpack_message`.

---

## What’s Actually Happening?

Basically, raw UDP just sends random bytes. This file makes sure those bytes mean something to our Python code:

*   **Packing:** Turns your variables (Task ID, Worker ID, etc.) into an 18-byte big-endian header, sticks your payload on the end, and calculates a CRC32 checksum so we know if the data got mangled.
*   **Unpacking:** Takes the incoming junk, checks the "Magic" bytes (`RJ`) and version, verifies the checksum, and gives you back a nice `Header` object and the raw payload.
*   **Safety:** If a packet is too short, has a bad checksum, or the wrong version, it throws a `ProtocolError`. Catch this in your loops so the worker/server doesn't crash on bad network noise.

---

## Wire Format (For the Curious)

If you need to know exactly how the bytes look on the wire (or if you're writing the report):

**Header Layout (18 Bytes Fixed)**
*   **Format:** `!HBB I HBB H I` (Big-Endian)

| Field | Size | Type | What it is |
| :--- | :--- | :--- | :--- |
| `Magic` | 2B | `uint16` | `0x524A` (The 'RJ' identifier) |
| `Version` | 1B | `uint8` | Currently `1` |
| `Msg_Type` | 1B | `uint8` | ID from 1 to 5 |
| `Task_ID` | 4B | `uint32` | Unique ID for the job |
| `Worker_ID` | 2B | `uint16` | ID of the worker |
| `Attempt_Num` | 1B | `uint8` | Which attempt this is |
| `Reserved` | 1B | `uint8` | Just `0x00` for alignment |
| `Payload_Len`| 2B | `uint16` | Body length (0–512) |
| `Checksum` | 4B | `uint32` | CRC32 of the payload |

---

## The Functions

### `pack_message(...)`
```python
packet = pack_message(msg_type, task_id=0, worker_id=0, attempt_num=0, payload=b"")
```
*   **Give it:** The message type and any IDs/payload.
*   **Get back:** A `bytes` object ready for `socket.sendto()`.

### `unpack_message(data)`
```python
header, payload = unpack_message(raw_bytes)
```
*   **Give it:** The raw bytes from `socket.recvfrom()`.
*   **Get back:** A `Header` object and the `payload` bytes.
*   **Careful:** Will raise `ProtocolError` if the packet is garbage (bad magic, bad CRC, etc.).

---

# Server Task Management (`task_manager.py`)

This module handles the server-side logic for tracking tasks, managing their lifecycle, and ensuring we don't process the same result twice if a worker retransmits.

**Note:** Use the `TaskManager` class to keep the server state clean. It tracks which worker is doing what and which tasks are finished.

---

## What’s Actually Happening?

The server needs to stay organized when multiple workers are asking for work and sending back results:

*   **State Tracking:** Every task goes through a lifecycle: `PENDING` -> `IN_FLIGHT` -> `COMPLETED`. This prevents the server from handing the same task to two different workers at the same time.
*   **Duplicate Suppression:** In unreliable networks (UDP), a worker might send a result, not get an ACK, and send it again. `TaskManager` keeps a set of `completed_task_ids` to catch and ignore these duplicates.
*   **Payload Management:** It stores the original task payloads and the results received from workers, associated with their unique `Task_ID`.

---

## Task Lifecycle

| Status | Meaning |
| :--- | :--- |
| `PENDING` | Task is loaded and waiting for a worker to request it. |
| `IN_FLIGHT` | Task has been dispatched to a worker but no result has been received yet. |
| `COMPLETED` | Result received and recorded. The task is done. |

---

## The `TaskManager` Methods

### `add_task(task_id, payload)`
*   Registers a new task in the system.
*   Initial status is set to `PENDING`.

### `get_next_pending_task(worker_id)`
```python
task_id, payload = manager.get_next_pending_task(worker_id)
```
*   **What it does:** Finds the first `PENDING` task, marks it `IN_FLIGHT`, assigns it to the `worker_id`, and records the dispatch time.
*   **Returns:** `(task_id, payload)` or `None` if nothing is left to do.

### `process_result(task_id, result_payload)`
```python
success = manager.process_result(task_id, result_payload)
```
*   **What it does:** Records the result and marks the task `COMPLETED`.
*   **Duplicate Check:** Returns `False` if the task was already completed (suppression). Returns `True` if this is the first time we're seeing this result.

### `all_completed()`
*   Returns `True` if every task registered has reached the `COMPLETED` state. Used to determine when the server can shut down.
