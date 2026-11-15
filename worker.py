"""A simple RJDAP worker client with reliable task-result delivery."""

import datetime
import os
import socket
import sys

from protocol import MessageType, ProtocolError, pack_message, unpack_message


DEFAULT_SERVER_IP = "127.0.0.1"
DEFAULT_SERVER_PORT = 5005
FAKE_RESULT = "done: 123"
DISPATCH_TIMEOUT_SECONDS = 5.0
ACK_TIMEOUT_SECONDS = 0.2


def log(
    worker_id,
    message,
    msg_type="EVENT",
    task_id="-",
    attempt_num="-",
    payload_len="-",
):
    """Print a timestamped message and append it to this worker's log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = (
        f"[{timestamp}] msg_type={msg_type} task_id={task_id} "
        f"attempt_num={attempt_num} payload_len={payload_len} {message}"
    )
    print(line, flush=True)

    os.makedirs("logs", exist_ok=True)
    with open(os.path.join("logs", f"worker_{worker_id}.log"), "a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")


def log_packet(worker_id, direction, header):
    """Log the common fields for a successfully decoded packet."""
    log(
        worker_id,
        direction + " " + header.msg_type.name,
        msg_type=header.msg_type.name,
        task_id=header.task_id,
        attempt_num=header.attempt_num,
        payload_len=header.payload_len,
    )


def send_result_reliably(sock, server, worker_id, task_id, result, max_retries=5):
    """Send a result up to max_retries times until its matching ACK arrives."""
    if (
        not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or not 1 <= max_retries <= 255
    ):
        raise ValueError("max_retries must be an integer from 1 to 255")

    result_payload = result.encode("utf-8")

    for attempt_num in range(1, max_retries + 1):
        packet = pack_message(
            MessageType.TASK_RESULT,
            task_id=task_id,
            worker_id=worker_id,
            attempt_num=attempt_num,
            payload=result_payload,
        )
        sock.sendto(packet, server)
        log(
            worker_id,
            "SEND TASK_RESULT",
            msg_type=MessageType.TASK_RESULT.name,
            task_id=task_id,
            attempt_num=attempt_num,
            payload_len=len(result_payload),
        )

        # A short timeout lets the worker retry if the ACK was lost.
        sock.settimeout(ACK_TIMEOUT_SECONDS)
        while True:
            try:
                data, address = sock.recvfrom(1024)
            except socket.timeout:
                log(
                    worker_id,
                    "ACK timeout; "
                    + ("retrying" if attempt_num < max_retries else "retry limit reached"),
                    msg_type=MessageType.TASK_RESULT.name,
                    task_id=task_id,
                    attempt_num=attempt_num,
                    payload_len=len(result_payload),
                )
                break

            try:
                header, payload = unpack_message(data)
            except ProtocolError as error:
                log(
                    worker_id,
                    f"BAD PACKET (ProtocolError) from {address}: {error}",
                    msg_type="INVALID",
                    payload_len=len(data),
                )
                continue

            log_packet(worker_id, "RECV", header)
            if header.msg_type == MessageType.ACK_RESULT and header.task_id == task_id:
                log(
                    worker_id,
                    "RECV ACK_RESULT confirmation",
                    msg_type=header.msg_type.name,
                    task_id=header.task_id,
                    attempt_num=header.attempt_num,
                    payload_len=header.payload_len,
                )
                return True

            if header.msg_type == MessageType.TASK_DISPATCH:
                log(
                    worker_id,
                    "NOTE TASK_DISPATCH received while waiting for ACK; "
                    "not queued in this prototype",
                    msg_type=header.msg_type.name,
                    task_id=header.task_id,
                    attempt_num=header.attempt_num,
                    payload_len=header.payload_len,
                )
            elif header.msg_type == MessageType.ACK_RESULT:
                log(
                    worker_id,
                    f"IGNORE ACK_RESULT; waiting for task_id={task_id}",
                    msg_type=header.msg_type.name,
                    task_id=header.task_id,
                    attempt_num=header.attempt_num,
                    payload_len=header.payload_len,
                )

    log(
        worker_id,
        f"GAVE UP TASK_RESULT after {max_retries} attempts",
        msg_type=MessageType.TASK_RESULT.name,
        task_id=task_id,
        attempt_num=max_retries,
        payload_len=len(result_payload),
    )
    return False


def parse_arguments(arguments):
    """Read optional worker and server settings from the command line."""
    if len(arguments) > 3:
        raise ValueError("Usage: python worker.py [worker_id] [server_ip] [server_port]")

    worker_id = int(arguments[0]) if len(arguments) >= 1 else 1
    server_ip = arguments[1] if len(arguments) >= 2 else DEFAULT_SERVER_IP
    server_port = int(arguments[2]) if len(arguments) >= 3 else DEFAULT_SERVER_PORT
    return worker_id, (server_ip, server_port)


def main():
    try:
        worker_id, server = parse_arguments(sys.argv[1:])
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    worker_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Send a join message so the server knows this worker is available.
        join_packet = pack_message(MessageType.WORKER_JOIN, worker_id=worker_id)
        worker_socket.sendto(join_packet, server)
        log(
            worker_id,
            f"SEND WORKER_JOIN server={server[0]}:{server[1]}",
            msg_type=MessageType.WORKER_JOIN.name,
            task_id=0,
            attempt_num=0,
            payload_len=0,
        )

        # Wait for the first task, ignoring valid packets of other message types.
        worker_socket.settimeout(DISPATCH_TIMEOUT_SECONDS)
        while True:
            try:
                data, address = worker_socket.recvfrom(1024)
            except socket.timeout:
                log(
                    worker_id,
                    "Server not responding; no TASK_DISPATCH within 5 seconds",
                    msg_type="NONE",
                )
                return 0
            except ConnectionResetError:
                log(
                    worker_id,
                    "Server not responding; connection refused: server is not running",
                    msg_type="NONE",
                )
                return 0
            except ConnectionRefusedError:
                log(
                    worker_id,
                    "Server not responding; connection refused: server is not running",
                    msg_type="NONE",
                )
                return 0

            try:
                header, payload = unpack_message(data)
            except ProtocolError as error:
                log(
                    worker_id,
                    f"BAD PACKET (ProtocolError) from {address}: {error}",
                    msg_type="INVALID",
                    payload_len=len(data),
                )
                continue

            log_packet(worker_id, "RECV", header)
            if header.msg_type != MessageType.TASK_DISPATCH:
                log(
                    worker_id,
                    f"IGNORE {header.msg_type.name} while waiting for TASK_DISPATCH",
                    msg_type=header.msg_type.name,
                    task_id=header.task_id,
                    attempt_num=header.attempt_num,
                    payload_len=header.payload_len,
                )
                continue

            task_text = payload.decode("utf-8", errors="replace")
            log(
                worker_id,
                f"TASK payload={task_text}",
                msg_type=header.msg_type.name,
                task_id=header.task_id,
                attempt_num=header.attempt_num,
                payload_len=header.payload_len,
            )
            break

        # Phase 1 uses a predictable fake result instead of doing real work.
        send_result_reliably(
            worker_socket,
            server,
            worker_id,
            header.task_id,
            FAKE_RESULT,
        )
        return 0
    finally:
        # Close the UDP socket even if an error or timeout occurs.
        worker_socket.close()


if __name__ == "__main__":
    sys.exit(main())
