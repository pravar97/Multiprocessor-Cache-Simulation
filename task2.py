import sys

cs = set()


class SRAM:
    """
    This SRAM class is represent SRAM memory, which stores its contents in the list: items and has
    a limit of 8 items. It got various functions to interact with the SRAM
    """

    def __init__(self):

        self.limit = 21  # Each block is 48 bytes, 4 words of 8 bytes, 4 addresses of 4 bytes( assuming 32 bit
        # addressing) 8 x 4 + 4 x 4 = 48, 1024/48 = 21

        self.items = []

    def add_item(self, tag, index):

        block = (tag, index)
        self.items = [x for x in self.items if x != block][1 - self.limit:] + [block]
        # Removes duplicates and removes earlier items to preserve the limit, add block at end so its removed last
        return 1

    def remove_item(self, tag, index):

        block = (tag, index)
        self.items = [x for x in self.items if x != block]
        return 1

    def get_item(self, tag, index, clock=0):

        block = (tag, index)
        if block in self.items:
            self.remove_item(tag, index)  # Save space by removing the read item
            return True, clock + 2
        else:
            return False, clock + 2


class AccessType:
    """
    This Class is designed to simplify updating number of accesses, by calling the type of
    access in various parts of the program, the property access_type maintains the access_type
    with highest level, for example if we have an off-chip access in one operation then we cannot
    update to a private access in this same memory operation
    """

    def __init__(self):
        self.access_type = 'private'  # Initially this is the lowest type of access which we default to in beginning

        # This is to minimise code in updating the relevant statistics
        self.types = {'private': (0, 'Private-accesses', 'Priv-average-latency'),
                      'remote': (1, 'Remote-accesses', 'Rem-average-latency'),
                      'off-chip': (2, 'Off-chip-accesses', 'Off-chip-average-latency')}

    # Whenever in the program we access a certain part of memory, we call this
    def type_accessed(self, access_type):
        if self.types[access_type][0] > self.types[self.access_type][0]:
            self.access_type = access_type

    # return relevant key for updating relevant statistics
    def get_type(self):
        return self.types[self.access_type][1]

    # return relevant key for updating relevant statistics
    def get_latency_type(self):
        return self.types[self.access_type][2]

    # This is run at the start of each new memory operation
    def reset(self):
        self.access_type = 'private'


class Processor:
    """
    Processor class to represent each processor, it stores the processor id in self.p and the all the cache_lines,
    Functions represent operations in the processor which can return a clock to represent the latency of that function
    """

    def __init__(self, i):
        self.p = i
        self.lines = [{'state': 'i', 'tag': -1} for _ in range(512)]

    # Cache probe, gets the state if the tags match otherwise perform an eviction and return i for invalid
    def get_state(self, index, tag, clock=0):

        cache_line = self.lines[index]
        if cache_line['tag'] == tag:
            state = cache_line['state']
        else:
            self.update_state(index, tag, 'i')
            state = 'i'
        return state, clock + 1

    # Cache probe for updating the state and handling evictions
    def update_state(self, index, tag, new_state):

        if tag != self.lines[index]['tag']:
            if self.lines[index]['state'] != 'i':
                directory.update_state(index, self.lines[index]['tag'], self.p, 'i')
                # sram.add_item(self.lines[index]['tag'], index)  # Clock overlapped, since we don't need to wait to ensure
                # this is complete
                if self.lines[index]['state'] == 'm':
                    statistics['Replacement-writebacks'] += 1  # Since an eviction occurs to modified state we have to
                    # write back

            self.lines[index]['tag'] = tag

        self.lines[index]['state'] = new_state

        directory.update_state(index, tag, self.p, new_state)
        return 1

    # Read cache operation
    def read_cache(self, index, tag):

        state, clock = self.get_state(index, tag)
        if state != 'i':
            at.type_accessed('private')
            return clock + 1
        else:
            at.type_accessed('remote')
            in_sram, clock = sram.get_item(tag, index, clock)
            if not in_sram:
                par_clocks = [0]
                cancelled, par_clocks[0] = directory.check_requests(index, tag, self.p, clock)
                if not cancelled:  # cancelled when no sharers found by directory,
                    # then the below operation will be stopped by directory
                    par_clocks.append(
                        processor[(self.p + 1) % 4].forward_request(index, tag, self.p) + 3 + clock)
                clock = max(par_clocks)  # Since multiple operations run in parallel, choose the slowest one
            clock += self.update_state(index, tag, 's')
            return clock + 1

    # Write to the cache
    def write_cache(self, index, tag):

        state, clock = self.get_state(index, tag)
        if state == 'm':
            at.type_accessed('private')
            return clock + 1
        else:
            at.type_accessed('remote')
            par_clocks = [0]
            cancelled, par_clocks[0] = directory.check_invalidates(index, tag, self.p, state, clock)
            par_clocks.append(sram.remove_item(tag, index) + clock)  # invalidate SRAM too, Clock for this will be
            # overlapped

            get_data = int(state == 'i')
            if not cancelled:  # cancelled when no sharers found by directory,
                # then the below operation will be stopped by directory

                par_clocks.append(
                    processor[(self.p + 1) % 4].forward_invalidate(index, tag, self.p, get_data) + 3 + clock)
            clock = max(par_clocks)  # Since multiple operations run in parallel, choose the slowest one
            clock += self.update_state(index, tag, 'm')
            return clock + 1

    # This function is called during a read to get the sharers by looping through the ring
    def forward_invalidate(self, index, tag, host, get_data):
        if host == self.p:  # Base case we have looped round, nothing to be done here
            return 0

        # Forward message, while in parallel check if this processor is a sharer, add 3 per hop
        par_clocks = [processor[(self.p + 1) % 4].forward_invalidate(index, tag, host, get_data) + 3]
        state, tag_stored, clock = self.lines[index]['state'], self.lines[index]['tag'], 1
        if state != 'i' and tag == tag_stored:
            statistics['Invalidations-sent'] += 1
            clock = self.update_state(index, tag, 'i')
            par_clocks.append(clock + ((host - self.p) % 4) * 3 + get_data)
        return max(par_clocks)  # Return whatever is the bottleneck, for clock frequency

    def forward_request(self, index, tag, host):

        if host == self.p:  # Base case we have looped round, nothing to be done here
            return 0

        # Forward message, while in parallel check if this processor is a sharer, add 3 per hop
        clockf = processor[(self.p + 1) % 4].forward_request(index, tag, host) + 3
        state, tag_stored, clock = self.lines[index]['state'], self.lines[index]['tag'], 1
        if state == 'i' or tag != tag_stored:
            return clockf  # Since this processor is not a sharer, we discard what this processor was doing,
            # and use the result of another

        if state == 'm' and tag == tag_stored:
            statistics['Coherence-writebacks'] += 1
            self.update_state(index, tag, 's')

        return clock + ((host - self.p) % 4) * 3 + 1

    # Used by the directory to get this processor to load some extra data into SRAM to reduce cold misses
    def send_to_sram(self, tag, index):

        sram.add_item(tag, index)


class Directory:
    """
    The Directory class is to store the states of every cache line as well as their tags, the directory has
    operations that are received by other processors and also the directory can call other processor operations
    """

    def __init__(self):
        self.lines = [{} for _ in range(512)]

    # This is called by a processor which requires data as a result of read miss
    def check_requests(self, index, tag, p, clock=0):
        clock += 6  # Latency to access directory is 5 plus a directory look-up, 6.
        par_clocks = []  # Keeps track of the latency of every processor
        if tag not in self.lines[index]:
            self.lines[index][tag] = ['i', 'i', 'i', 'i']

        # Cancelled set to true when there are no sharers, therefore cancel the share operation in every processor
        cancelled = not bool([x for i, x in enumerate(self.lines[index][tag]) if i != p and x != 'i'])
        if not cancelled:
            return cancelled, clock + 5

        # No sharers found, do a memory access, 20 cycles (15 for memory and 5 for directory to forward)
        at.type_accessed('off-chip')

        # Getting 3 extra memory items to reduce cold misses
        extra_items = []
        n = 1
        while len(extra_items) < 3:
            ntag = tag + ((index + n) >> 9)
            nindex = (index + n) % 512
            if self.lines[nindex].get(ntag, ['i', 'i', 'i', 'i']) == ['i', 'i', 'i', 'i']:
                extra_items.append((ntag, nindex))
            n += 1
        i = (p - 1) % 4

        for item in extra_items:
            processor[i].send_to_sram(item[0], item[1])
            i = (i - 1) % 4

        return cancelled, clock + 20

    # This is called by a processor in write miss, to invalid other processors and get data if need be
    def check_invalidates(self, index, tag, p, prev_state, clock=0):

        clock += 6  # Latency to access directory is 5 plus a directory look-up, 6.
        par_clocks = [5]  # Keeps track of the latency of every processor,
        # 5 is the default if no other processors are sharing the data

        if tag not in self.lines[index]:
            self.lines[index][tag] = ['i', 'i', 'i', 'i']

        # Cancelled set to true when there are no sharers, therefore cancel the share operation in every processor
        cancelled = not bool([x for i, x in enumerate(self.lines[index][tag]) if i != p and x != 'i'])
        if cancelled and prev_state == 'i':  # Get data if the prev state is invalid
            par_clocks.append(20)
            at.type_accessed('off-chip')

            # Getting 3 extra memory items to reduce cold misse
            extra_items = []
            n = 1
            while len(extra_items) < 3:
                ntag = tag + ((index + n) >> 9)
                nindex = (index + n) % 512
                if self.lines[nindex].get(ntag, ['i', 'i', 'i', 'i']) == ['i', 'i', 'i', 'i']:
                    extra_items.append((ntag, nindex))
                n += 1
            i = (p - 1) % 4
            for item in extra_items:
                processor[i].send_to_sram(item[0], item[1])
                i = (i - 1) % 4

        return cancelled, clock + max(
            par_clocks)  # We add the latency of the slowest operation happening in parallel

    # Update the directory state
    def update_state(self, index, tag, p, new_state):

        if tag not in self.lines[index]:
            self.lines[index][tag] = ['i', 'i', 'i', 'i']
        self.lines[index][tag][p] = new_state


# Converts a trace file to a list of memory operations,
# where a memory operation is a 3 element list with structure [Processor, operation (R or W), address]
# except modes such as v, p and h can be single item lists
def get_trace(filename):
    with open(filename, 'r') as f:
        trace = f.read().splitlines()
    return [t.split(' ') for t in trace]


# Convert memory address to a tag and index, we don't care about byte offset
def get_index_tag(address):
    address = int(address)
    index = (address & 0b11111111100) >> 2
    tag = address >> 11
    return index, tag


# Entry point for task 1
def task2(filename):
    trace = get_trace(filename)

    clock = 0

    v = False  # initially V mode is off

    # Dictionaries to save code in conversions
    readwrite = {'R': 'read', 'W': 'write'}
    states2text = {'i': 'Invalid (cache miss)', 's': 'Shared', 'm': 'Modified'}

    for t in trace:
        if t[0].lower() == 'v':  # Display line by line details
            v = not v  # If v mode on, then off else on
            continue
        elif t[0].lower() == 'p':  # Display current state of caches
            for p in processor:

                print('P' + str(p.p))
                for i, j in enumerate(p.lines):
                    if j['state'] != 'i':
                        print('cache-line: ' + str(i) + '  ' + str(j))
                print()

            continue
        elif t[0].lower() == 'h':  # Display hit rate so far
            total = statistics['Private-accesses'] + statistics['Remote-accesses'] + statistics['Off-chip-accesses']
            if total:
                print('Hit-Rate: ' + str(statistics['Private-accesses'] * 100 / total) + '%')
            else:
                print('Hit-Rate: 100%')
            continue

        at.reset()  # Reset the access type to private as default, since this is lowest access type so far
        p = int(t[0][1])  # Processor number
        operation = t[1]  # W or R
        index, tag = get_index_tag(t[2])
        init_states = directory.lines[index].get(tag, ['i', 'i', 'i', 'i']).copy()  # Used for line by line feedback

        if operation == 'R':

            clock = processor[p].read_cache(index, tag)

        elif operation == 'W':

            clock = processor[p].write_cache(index, tag)

        if v:  # If in V mode, do line by line feedback
            init_states[p] = states2text[init_states[p]]
            if 'm' in init_states:
                rest = ' and found in state Modified in the cache of P' + str(init_states.index('m'))
            elif init_states.count('s') == 3:
                i = [str(x) for x in range(0, 4) if init_states[x] == 's']
                rest = ' and found in state Shared in the cache of P' + i[0] + ', ' + 'P' + i[1] + ' and P' + i[2]
            elif init_states.count('s') == 2:
                i = [str(x) for x in range(0, 4) if init_states[x] == 's']
                rest = ' and found in state Shared in the cache of P' + i[0] + ' and P' + i[1]
            elif init_states.count('s') == 1:
                rest = ' and found in state Shared in the cache of P' + str(init_states.index('s'))
            else:
                rest = ''

            print('A ' + readwrite[t[1]] + ' by processor ' + t[0] + ' to word ' + t[2] +
                  ' looked for tag ' + str(tag) + ' in cacheline/block ' + str(index) +
                  ', was found in state ' + init_states[p] +
                  ' in this cache' + rest)

        statistics[at.get_type()] += 1
        if at.get_type() == 'Off-chip-accesses' and t[1] == 'W':
            cs.add(clock)
        statistics[at.get_latency_type()] += clock
        statistics['Total-latency'] += clock

    statistics['Average-latency'] = statistics['Total-latency'] / len(trace)
    try:
        statistics['Priv-average-latency'] /= statistics['Private-accesses']
    except:
        pass
    try:
        statistics['Rem-average-latency'] /= statistics['Remote-accesses']
    except:
        pass
    try:
        statistics['Off-chip-average-latency'] /= statistics['Off-chip-accesses']
    except:
        pass

    statistics['Total-accesses'] = statistics['Private-accesses'] + statistics['Remote-accesses'] + statistics[
        'Off-chip-accesses']
    out = []
    for k, v in statistics.items():
        out.append(k + ': ' + str(v) + '\n')
    with open('out_task2_' + filename, 'w') as f:
        f.writelines(out)


at = AccessType()
processor = [Processor(i) for i in range(0, 4)]
directory = Directory()
sram = SRAM()
statistics = {'Private-accesses': 0,
              'Remote-accesses': 0,
              'Off-chip-accesses': 0,
              'Total-accesses': 0,
              'Replacement-writebacks': 0,
              'Coherence-writebacks': 0,
              'Invalidations-sent': 0,
              'Average-latency': 0.0,
              'Priv-average-latency': 0.0,
              'Rem-average-latency': 0.0,
              'Off-chip-average-latency': 0.0,
              'Total-latency': 0}

if __name__ == '__main__':
    task2(sys.argv[1])
