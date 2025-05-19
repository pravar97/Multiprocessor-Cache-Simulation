# Multiprocessor-Cache-Simulation

## Task 1

Task 1 is implemented in the python file: `task1.py`.

It can be called using one of the following commands, where `<filename>` is the name of the trace file to be read:

* `./run-script.sh <filename>`
* `python3 task1.py <filename>`
* `python3 run.py <filename>`

Task 1 is implemented using multiple classes:

* **`Processor` Class**: Represents each processor.
    * `p`: Field for the processor ID.
    * `lines`: A list of 512 dictionaries. Each dictionary represents one cache line and stores the `tag` and the `state` of that cache line.
    * The class includes various functions to represent the different operations a processor can perform.

* **`AccessType` Class**: Used to keep track of accesses performed, which helps in updating statistics.

* **`Directory` Class**: Stores all states for every tag, cache line, and processor. It has functions to represent directory operations.

The `task1` function, located at the bottom of the `task1.py` file, reads the trace file and processes each memory operation. It calls the relevant processor's function, which then modifies its relevant fields and calls functions in the `Directory` class when necessary.

## Task 2

Task 2 is implemented in the python file: `task2.py`.

It can be called using one of the following commands, where `<filename>` is the name of the trace file to be read:

* `./run-script.sh <filename> optimize`
* `python3 task2.py <filename>`
* `python3 run.py <filename> optimize`

The implementation of Task 2 is very similar to Task 1. However, the functions have been modified to achieve optimization, and an additional `SRAM` class has been added.

* **`SRAM` Class**: This class stores 21 blocks.
    * A block is 48 bytes because it contains four 8-byte words, each with a 4-byte address (assuming 32-bit addressing).
    * The total SRAM space is 1024 bytes. Therefore, 21 blocks (21 blocks * 48 bytes/block = 1008 bytes) can fit into the SRAM.

---

If you encounter a "permission denied" error when trying to run the script, execute the following command first to make the script executable:

```bash
chmod +x run-script.sh
