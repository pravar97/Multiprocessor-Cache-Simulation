import sys
from task1 import task1
from task2 import task2
filename = sys.argv[1]


if sys.argv[2].lower() == 'optimize':
    print('Optimized version running...')
    task2(filename)
else:
    print('Unoptimized version running... Please enter: \'./run-script.sh <filename> optimize\' for optimized version')
    task1(filename)


