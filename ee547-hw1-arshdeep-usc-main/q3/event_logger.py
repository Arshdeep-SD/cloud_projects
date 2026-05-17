import os
from pathlib import Path
from dataclasses import dataclass
from message_source import MessageSource, Packet


@dataclass
class LoggerStats:
    packets_received: int = 0
    packets_written: int = 0
    duplicates_discarded: int = 0
    corrupted_packets: int = 0
    retransmit_requests: int = 0
    retransmits_received: int = 0
    inversions: int = 0
    gaps: int = 0
    buffer_flushes: int = 0
    final_buffer_size: int = 0
    # crashes removed


class EventLogger:
    def __init__(self,
                 source: MessageSource,
                 log_file: Path,
                 buffer_size: int = 30):
        """
        Initialize event logger.

        Args:
            source: Message source to receive from
            log_file: Path to append-only log file
            buffer_size: Max packets to buffer before forced flush
        """
        self.source = source
        self.log_file = log_file
        self.buffer_size = buffer_size

        # Core state
        self.buffer: dict[int, Packet] = {}
        self.seen_sequences: set[int] = set()
        self.pending_retransmits: set[int] = set()
        self.gap_tracker: dict[int, int] = {}
        self.last_written_seq: int = -1
        self.crashes: int = 0  # moved here

        self.stats = LoggerStats()

        # Clear log at start
        if self.log_file.exists():
            self.log_file.unlink()

        self._recover_state()

    # ----------------------------
    # Public API
    # ----------------------------

    def run(self) -> LoggerStats:
        """
        Main processing loop.

        Continuously receive packets until termination.
        """
        while True:
            seen_before = len(self.seen_sequences)
            delivered_any = False

            try:
                while True:
                    pkt = self.source.receive()
                    if pkt is None:
                        break

                    self._handle_packet(pkt)

                    if self._should_flush():
                        self._flush_buffer()

            except SystemExit:
                self.crashes += 1
                print(f"Simulated crash caught! Total crashes: {self.crashes}")
                print(
                    f"Coverage: {self.stats.packets_written}/{self.source.total_packets}, "
                    f"Inversions: {self.stats.inversions}, "
                    f"Lost in buffer: {len(self.buffer)}\n"
                )
                self._restart_source()
                continue

            # Request any still-missing packets
            missing = (
                set(self.source.get_ground_truth())
                - self.seen_sequences
                - self.pending_retransmits
            )

            for seq in missing:
                self._request_retransmit(seq)

            # Drain retransmits
            for _ in range(len(self.pending_retransmits)):
                pkt = self.source.receive()
                if pkt is not None:
                    delivered_any = True
                    self._handle_packet(pkt)

            self._flush_buffer()

            # Termination condition
            if len(self.seen_sequences) == seen_before and not delivered_any:
                break

            self._restart_source()

        self._finalize()
        return self.stats

    # ----------------------------
    # Packet handling
    # ----------------------------

    def _handle_packet(self, packet: Packet) -> None:
        """Process a single packet."""
        seq = packet.sequence
        self.stats.packets_received += 1

        # Corruption check
        if not self.source.verify_checksum(packet):
            self.stats.corrupted_packets += 1
            self._request_retransmit(seq)
            return

        # Duplicate check
        if seq in self.seen_sequences:
            self.stats.duplicates_discarded += 1
            return

        # Retransmit bookkeeping
        if seq in self.pending_retransmits:
            self.pending_retransmits.discard(seq)
            self.stats.retransmits_received += 1

        # Gap detection
        expected = self.last_written_seq + 1
        for missing in range(expected, seq):
            if missing not in self.seen_sequences and missing not in self.gap_tracker:
                self.gap_tracker[missing] = 0

        for missing in list(self.gap_tracker):
            self.gap_tracker[missing] += 1
            if self.gap_tracker[missing] > 15:
                self._request_retransmit(missing)
                self.stats.gaps += 1
                del self.gap_tracker[missing]

        self.gap_tracker.pop(seq, None)

        # Buffer packet
        self.buffer[seq] = packet
        self.seen_sequences.add(seq)

    # ----------------------------
    # Buffer / flushing
    # ----------------------------

    def _should_flush(self) -> bool:
        """Determine if buffer should be flushed."""
        return (
            (self.last_written_seq + 1) in self.buffer
            or len(self.buffer) >= self.buffer_size
        )

    def _flush_buffer(self) -> None:
        """Write buffered packets to log."""
        if not self.buffer:
            return

        wrote = False

        with open(self.log_file, "a") as f:
            # Sequential drain
            while (self.last_written_seq + 1) in self.buffer:
                pkt = self.buffer.pop(self.last_written_seq + 1)
                self._write_packet(f, pkt, "OK")
                self.last_written_seq = pkt.sequence
                wrote = True

            # Forced drain if buffer clogged
            if len(self.buffer) >= self.buffer_size:
                for seq in sorted(self.buffer.keys())[:5]:
                    pkt = self.buffer.pop(seq)
                    status = "LATE" if seq < self.last_written_seq else "OK"
                    if status == "LATE":
                        self.stats.inversions += 1

                    self.last_written_seq = max(self.last_written_seq, seq)
                    self._write_packet(f, pkt, status)
                    wrote = True

            if wrote:
                f.flush()
                os.fsync(f.fileno())
                self.stats.buffer_flushes += 1

    def _finalize(self) -> None:
        """Called after termination. Flush remaining buffer."""
        self._flush_buffer()
        self.stats.final_buffer_size = len(self.buffer)

    # ----------------------------
    # Helpers
    # ----------------------------

    def _write_packet(self, f, pkt: Packet, status: str) -> None:
        f.write(f"{pkt.sequence},{pkt.timestamp},{pkt.payload.hex()},{status}\n")
        self.stats.packets_written += 1

    def _request_retransmit(self, seq: int) -> None:
        if seq not in self.pending_retransmits:
            self.source.request_retransmit(seq)
            self.pending_retransmits.add(seq)
            self.stats.retransmit_requests += 1

    def _recover_state(self) -> None:
        """Scan existing log to recover last written sequence."""
        if not self.log_file.exists():
            return

        with open(self.log_file, "r") as f:
            for line in f:
                try:
                    seq = int(line.split(",", 1)[0])
                    self.seen_sequences.add(seq)
                    self.last_written_seq = max(self.last_written_seq, seq)
                except Exception:
                    break

    def _restart_source(self) -> None:
        self.source = MessageSource(
            seed=self.source.seed,
            total_packets=self.source.total_packets,
            reorder_window=self.source.reorder_window,
            duplicate_prob=self.source.duplicate_prob,
            loss_prob=self.source.loss_prob,
            corruption_prob=self.source.corruption_prob,
            termination_prob=self.source.termination_prob,
            state_dir=self.source._packets_file.parent,
        )
