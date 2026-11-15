"""A tiny one-task RJDAP server for testing worker.py."""

import datetime
import os
import socket
import sys

from protocol import MessageType, ProtocolError, pack_message, unpack_message


SERVER_IP = "127.0.0.1"
SERVER_PORT = 5005
TASK_ID = 1
TASK_PAYLOAD = b"dummy_payload_for_task_1"
MAX_RESULT_ATTEMPTS = 5
ACK_OPTIONS = {"--drop-first-ack", "--never-ack", "--wrong-ack-first"}
SUPPORTED_OPTIONS = ACK_OPTIONS | {"--send-garbage"}


def log(message):
    """Print one timestamped server message."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}", flush=True)


def log_packet(direction, header):
    """Log common details from a decoded packet."""
    log(
        f"{direction} {header.msg_type.name} task_id={header.task_id} "
        f"attempt_num={header.attempt_num} payload_len={header.payload_len}"
    )


def main():
    options = set(sys.argv[1:])
    if (
        len(options) != len(sys.argv) - 1
        or not options.issubset(SUPPORTED_OPTIONS)
        or len(options & ACK_OPTIONS) > 1
    ):
        print(
            "Usage: python mock_server.py "
            "[--drop-first-ack | --never-ack | --wrong-ack-first] [--send-garbage]",
            file=sys.stderr,
        )
        return 2

    drop_first_ack = "--drop-first-ack" in options
    never_ack = "--never-ack" in options
    wrong_ack_first = "--wrong-ack-first" in options
    send_garbage = "--send-garbage" in options
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server_socket.bind((SERVER_IP, SERVER_PORT))
        log(f"Listening on {SERVER_IP}:{SERVER_PORT}")

        # Wait for a worker to join before assigning the single test task.
        while True:
            data, worker_address = server_socket.recvfrom(1024)
            try:
                header, payload = unpack_message(data)
            except ProtocolError as error:
                log(f"BAD PACKET from {worker_address}: {error} (packet_len={len(data)})")
                continue

            log_packet("RECV", header)
            if header.msg_type == MessageType.WORKER_JOIN:
                worker_id = header.worker_id
                break
            log(f"IGNORE {header.msg_type.name}; waiting for WORKER_JOIN")

        if send_garbage:
            garbage = os.urandom(8)
            server_socket.sendto(garbage, worker_address)
            log(f"SEND GARBAGE payload_len={len(garbage)}")

        dispatch = pack_message(
            MessageType.TASK_DISPATCH,
            task_id=TASK_ID,
            worker_id=worker_id,
            payload=TASK_PAYLOAD,
        )
        server_socket.sendto(dispatch, worker_address)
        log(
            f"SEND TASK_DISPATCH task_id={TASK_ID} attempt_num=0 "
            f"payload_len={len(TASK_PAYLOAD)}"
        )

        first_result = True
        result_count = 0
        while True:
            data, address = server_socket.recvfrom(1024)
            try:
                header, payload = unpack_message(data)
            except ProtocolError as error:
                log(f"BAD PACKET from {address}: {error} (packet_len={len(data)})")
                continue

            log_packet("RECV", header)
            if header.msg_type != MessageType.TASK_RESULT or header.task_id != TASK_ID:
                log("IGNORE packet; waiting for the result of the test task")
                continue

            log(f"RESULT task_id={header.task_id} payload={payload.decode('utf-8', errors='replace')}")
            result_count += 1
            if never_ack:
                log(f"NEVER ACK_RESULT attempt_num={header.attempt_num}")
                if result_count >= MAX_RESULT_ATTEMPTS:
                    log(f"Received {MAX_RESULT_ATTEMPTS} results; stopping without an ACK")
                    return 0
                continue

            if first_result and drop_first_ack:
                first_result = False
                log("DROP first ACK_RESULT to test worker retransmission")
                continue

            if first_result and wrong_ack_first:
                first_result = False
                wrong_ack = pack_message(
                    MessageType.ACK_RESULT,
                    task_id=TASK_ID + 998,
                    worker_id=worker_id,
                    attempt_num=header.attempt_num,
                )
                server_socket.sendto(wrong_ack, address)
                log(
                    f"SEND wrong ACK_RESULT task_id={TASK_ID + 998} "
                    f"attempt_num={header.attempt_num} payload_len=0"
                )
                continue

            ack = pack_message(
                MessageType.ACK_RESULT,
                task_id=TASK_ID,
                worker_id=worker_id,
                attempt_num=header.attempt_num,
            )
            server_socket.sendto(ack, address)
            log(f"SEND ACK_RESULT task_id={TASK_ID} attempt_num={header.attempt_num} payload_len=0")
            return 0
    finally:
        server_socket.close()


if __name__ == "__main__":
    sys.exit(main())
