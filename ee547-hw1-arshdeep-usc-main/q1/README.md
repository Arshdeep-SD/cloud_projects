## **Message Types**

| Message Type | Purpose |
|--------------|---------|
| `INIT`       | Exchange min, max, and length of local data to determine global range |
| `DATA`       | Send a chunk of up to 10 integers to the partner worker |
| `DONE`       | Notify partner that all data has been sent |
| `FIN`        | Notify partner that output has been written and worker has finished, only sent by A to B|

---

## **Merge Strategy**

1. Each worker sorts its local dataset.
2. Workers exchange their minimum and maximum values (`INIT`) to determine the **global range**.
3. Data is split at the midpoint of the global range:
   - Worker A keeps values `≤ split`, sends `> split` to B
   - Worker B keeps values `> split`, sends `≤ split` to A
4. Data is exchanged in **chunks of 10 integers** until all data is sent.
5. Each worker merges received data with its kept data, sorts it, and writes it to the output file.
6. Worker B waits for a `FIN` from A to preserve global ordering.

**Reason to use this strategy:**

- Simple and deterministic
- Memory-efficient
- Avoids repeated sorting 
- Supports asynchronous execution

---

## **Work Balancing**

- Workers divide the dataset by value ranges, roughly splitting the total workload in half.
- Chunked transfers ensure small incremental work per step, reducing memory spikes.
- Asynchronous steps allow both workers to process data in parallel.
- Final output ensures global ordering without complex synchronization.

---

## **Usage Example**

Refer to testing.ipynb for usage examples.


