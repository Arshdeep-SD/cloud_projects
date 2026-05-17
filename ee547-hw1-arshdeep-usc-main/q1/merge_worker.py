import json
import os
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Message:
    msg_type: str   # Max 5 chars
    values: list[int]  # Max 10 integers

@dataclass
class WorkerStats:
    comparisons: int      # Number of comparison operations
    messages_sent: int    # Number of messages written
    messages_received: int # Number of messages read
    values_output: int    # Number of values written to output


class MergeWorker:
    def __init__(self, worker_id, data, inbox, outbox, output, state_file):
        self.worker_id = worker_id
        self.data = sorted(data)  # Sort initially to make range finding O(1)
        self.inbox = Path(inbox)
        self.outbox = Path(outbox)
        self.output = Path(output)
        self.state_file = Path(state_file)
        self.stats = WorkerStats(0, 0, 0, 0)
        self.state = self._load_state()

    def _initial_state(self) -> dict:
        return {
            "phase": "INIT",
            "partner_min": None,
            "partner_max": None,
            "sent_all": False,
            "received_all": False,
            "buffer": [], # For incoming data
            "local_idx": 0,
            "partner_done": False
        }

    def _load_state(self) -> dict:
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return self._initial_state()

    def _save_state(self) -> None:
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f)

    def step(self) -> bool:
        # 1. Read Inbox
        received_msg = None
        if self.inbox.exists() and os.path.getsize(self.inbox) > 0:
            try:
                with open(self.inbox, 'r') as f:
                    received_msg = json.load(f)
                self.stats.messages_received += 1
                open(self.inbox, 'w').close() # Clear inbox after reading
            except json.JSONDecodeError:
                pass

        # 2. Update State & 3. Prepare Message
        out_msg = None
        
        if self.state["phase"] == "INIT":
            # Send range info
            out_msg = {"msg_type": "INIT", "values": [min(self.data), max(self.data), len(self.data)]}
            if received_msg and received_msg["msg_type"] == "INIT":
                self.state["partner_min"] = received_msg["values"][0]
                self.state["partner_max"] = received_msg["values"][1]
                self.state["phase"] = "MERGE"

        elif self.state["phase"] == "MERGE":
            # Determine split (midpoint of total range)
            global_min = min(min(self.data), self.state["partner_min"])
            global_max = max(max(self.data), self.state["partner_max"])
            split = (global_min + global_max) // 2

            # Filter data to send to partner
            if self.worker_id == "A":
                # A sends values > split to B
                to_send = [x for x in self.data if x > split][self.state["local_idx"]:self.state["local_idx"]+10]
            else:
                # B sends values <= split to A
                to_send = [x for x in self.data if x <= split][self.state["local_idx"]:self.state["local_idx"]+10]

            if to_send:
                out_msg = {"msg_type": "DATA", "values": to_send}
                self.state["local_idx"] += len(to_send)
            else:
                out_msg = {"msg_type": "DONE", "values": []}
                self.state["sent_all"] = True

            if received_msg:
                if received_msg["msg_type"] == "DATA":
                    self.state["buffer"].extend(received_msg["values"])
                elif received_msg["msg_type"] == "DONE":
                    self.state["received_all"] = True

            if self.state["sent_all"] and self.state["received_all"]:
                self.state["phase"] = "OUT"

        elif self.state["phase"] == "OUT":
            # Combine local kept data with buffered data
            global_min = min(min(self.data), self.state["partner_min"])
            global_max = max(max(self.data), self.state["partner_max"])
            split = (global_min + global_max) // 2
            
            if self.worker_id == "A":
                kept = [x for x in self.data if x <= split]
                final_list = sorted(kept + self.state["buffer"])
                self.stats.comparisons += len(final_list) # Simplified tracking
                self._write_to_output(final_list)
                out_msg = {"msg_type": "FIN", "values": []}
                self.state["phase"] = "END"
            else:
                # B waits for A to finish so output is ordered
                if received_msg and received_msg["msg_type"] == "FIN":
                    kept = [x for x in self.data if x > split]
                    final_list = sorted(kept + self.state["buffer"])
                    self.stats.comparisons += len(final_list)
                    self._write_to_output(final_list)
                    self.state["phase"] = "END"

        # 4. Write to Outbox
        if out_msg:
            with open(self.outbox, 'w') as f:
                json.dump(out_msg, f)
            self.stats.messages_sent += 1

        self._save_state()
        return self.state["phase"] != "END"

    def _write_to_output(self, values):
        with open(self.output, 'a') as f:
            for v in values:
                f.write(f"{v}\n")
                self.stats.values_output += 1

    def get_stats(self):
        return self.stats