## 1. Buffer Size Choice

The buffer holds packets that arrive out of order. A size of 30 was chosen to strike a balance: it is large enough to handle temporary packet reordering while keeping memory usage reasonable. 

- **Effects of buffer size:**
  - Too small: forces early flush of slightly out-of-order packets, increasing the number of late packets and inversions in the log.
  - Too large: increases memory usage and can delay logging, which could risk losing packets in case of a crash.

The goal is to tolerate moderate out-of-order arrivals without using excessive memory or delaying logging unnecessarily.

---

## 2. Flush Strategy

Flushing occurs under two main conditions:

1. **Sequential packet available:**  
   If the next expected sequence number is in the buffer, it is written immediately. This keeps the log in order and reduces inversions.

2. **Buffer full:**  
   If the buffer reaches its maximum size, a small number of packets are force-flushed even if they are out of order. Out-of-order packets are marked as late in the log.

**Trade-offs:**  
- Sequential flushing ensures ordered logging and minimal inversions.  
- Forced flush prevents memory overflow but may generate late packets and increase inversion counts.  
- The number of packets flushed during forced flushes is chosen as a compromise between memory management and log ordering.

---

## 3. Gap Handling Approach

Gaps are tracked for missing sequence numbers:

- When a packet arrives, any missing sequences between the last written packet and the new packet are added to a gap tracker.  
- Each gap is counted over multiple iterations. If a gap persists beyond a threshold (15 cycles), a retransmit request is sent.  

**Reasoning for the threshold:**  
- Allows minor reordering without triggering unnecessary retransmit requests.  
- Reduces network traffic caused by premature retransmits.

**Trade-offs:**  
- A low threshold can result in excessive retransmits and duplicates.  
- A high threshold can delay recovery for truly lost packets, leaving temporary gaps in the log.

---

## 4. Trade-offs Observed During Testing

| Design Choice                     | Pros                                             | Cons / Observations                                     |
|----------------------------------|-------------------------------------------------|---------------------------------------------------------|
| Buffer size of 30                 | Handles moderate reordering, avoids memory issues | Bursts exceeding buffer can increase late packets      |
| Sequential flush when available   | Keeps log ordered, reduces inversions          | Small buffer flushes too often if network heavily reorders |
| Forced flush when buffer full     | Prevents unbounded memory growth               | Generates late packets and increases inversions        |
| Gap tracker threshold of 15       | Avoids unnecessary retransmits                 | Lost packets take longer to recover                     |
| Writing one packet at a time      | Simple, reliable, easy to recover              | Slightly slower for high-volume streams                |
| Restarting source on crash        | Ensures robustness to simulated crashes       | Resets can generate duplicates, handled by seen sequences |

---

# **Usage Example**

Refer to testing.ipynb for usage examples.

