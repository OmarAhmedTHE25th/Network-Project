from dataclasses import dataclass
from enum import IntEnum
import struct
import zlib

MAGIC_NUMBER = 0x524A  # protocol identifier
PROTOCOL_VERSION = 1
MAX_PAYLOAD_SIZE = 512  #  constraint: <= 512 bytes

# Network Byte Order (Big-Endian '!'):
# H: uint16 (Magic)
# B: uint8  (Version)
# B: uint8  (Msg_Type)
# I: uint32 (Task_ID)
# H: uint16 (Worker_ID)
# B: uint8  (Attempt_Num)
# B: uint8  (Reserved/Padding)
# H: uint16 (Payload_Len)
# I: uint32 (Payload_Checksum)
HEADER_FORMAT = "!HBB I HBB H I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 18 bytes


class MessageType(IntEnum):
    WORKER_JOIN = 1  
    HEARTBEAT = 2  
    TASK_DISPATCH = 3  
    TASK_RESULT = 4  
    ACK_RESULT = 5  


class ProtocolError(Exception):
    """Custom exception raised when packet decoding or validation fails."""

    pass


@dataclass
class Header:
    magic: int
    version: int
    msg_type: MessageType
    task_id: int
    worker_id: int
    attempt_num: int
    payload_len: int
    checksum: int


def pack_message(
    msg_type: MessageType,
    task_id: int = 0,
    worker_id: int = 0,
    attempt_num: int = 0,
    payload: bytes = b"",
) -> bytes:
    """Serializes header metadata and raw payload into binary UDP datagram."""
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Payload exceeds limit: {len(payload)} > {MAX_PAYLOAD_SIZE} bytes"  
        )

    # Compute CRC32 checksum over the payload (0 if empty)
    checksum = zlib.crc32(payload) & 0xFFFFFFFF if payload else 0
    payload_len = len(payload)
    reserved = 0

    header_bytes = struct.pack(
        HEADER_FORMAT,
        MAGIC_NUMBER,
        PROTOCOL_VERSION,
        int(msg_type),  
        task_id,  
        worker_id,  
        attempt_num,  
        reserved,
        payload_len,
        checksum,  
    )
    return header_bytes + payload


def unpack_message(data: bytes) -> tuple[Header, bytes]:
    """Deserializes raw datagram bytes into Header dataclass and payload bytes.
    Validates magic bytes, packet size, and payload integrity.
    """
    if len(data) < HEADER_SIZE:
        raise ProtocolError(
            f"Packet truncated: got {len(data)} bytes, expected at least {HEADER_SIZE}"
        )

    header_part = data[:HEADER_SIZE]
    (
        magic,
        version,
        msg_type_raw,
        task_id,
        worker_id,
        attempt_num,
        _,  # reserved
        payload_len,
        expected_checksum,
    ) = struct.unpack(
        HEADER_FORMAT, header_part
    )  

    if magic != MAGIC_NUMBER:
        raise ProtocolError(f"Invalid magic number: {hex(magic)}")

    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"Unsupported protocol version: {version}")

    try:
        msg_type = MessageType(msg_type_raw)
    except ValueError:
        raise ProtocolError(f"Unknown message type: {msg_type_raw}")

    payload = data[HEADER_SIZE:]

    if len(payload) != payload_len:
        raise ProtocolError(
            f"Payload length mismatch: expected {payload_len}, got {len(payload)}"
        )

    # Verify checksum if payload exists
    if payload_len > 0:
        actual_checksum = zlib.crc32(payload) & 0xFFFFFFFF
        if actual_checksum != expected_checksum:
            raise ProtocolError(
                f"Checksum mismatch: expected {expected_checksum}, calculated {actual_checksum}"  
            )

    header = Header(
        magic=magic,
        version=version,
        msg_type=msg_type,
        task_id=task_id,
        worker_id=worker_id,
        attempt_num=attempt_num,
        payload_len=payload_len,
        checksum=expected_checksum,
    )

    return header, payload