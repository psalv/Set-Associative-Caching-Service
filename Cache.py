
import threading
import time
from enum import Enum


# TODO: I probably want to package these classes within the Cache class, these interfaces don't need to be public


class CacheAction(Enum):
    ADD = 0
    UPDATE = 1
    GET = 2


class ThreadNotifierFIFOList(object):

    class ListNode(object):

        def __init__(self, val):
            self.val = val
            self.next = None

        def __repr__(self):
            return str(self.val)

    def __init__(self, _condition):
        self._condition = _condition
        self._head = None
        self._tail = None

    def is_empty(self):
        return self._head is None

    def append(self, item):

        # if threads are asleep then wake them and make them do the worker

        self._condition.acquire()
        self._condition.notify_all()         # all of the threads will awaken
        self._condition.release()

        if self._head is None:
            self._head = ThreadNotifierFIFOList.ListNode(item)
            self._tail = self._head
        else:
            self._tail.next = ThreadNotifierFIFOList.ListNode(item)
            self._tail = self._tail.next

    def peek(self):
        if self._head is not None:
            return self._head.val
        else:
            return None

    def pop(self):
        if self._head:
            item = self._head.val
            self._head = self._head.next
            return item
        else:
            return None


class WorkerJob(object):

    def __init__(self, job_type, job_data):
        self.job_type = job_type
        self.job_data = job_data

    def __repr__(self):
        return str(self.job_type) + " - " + str(self.job_data)


class NWaySetAssociativeCache(object):

    def __init__(self, n=4, replacement_algorithm="LRU", lines=32):

        # Setting the replacement algorithm (Either LRU, MRU, or user-defined)
        self._replacement_algorithm = None
        if not self._set_replacement_algorithm(replacement_algorithm):
            raise ValueError("Replacement algorithm parameter must designate LRU or MRU or be a function.")

        self._number_of_sets = n
        self._lines_per_set = lines



        # TODO
        self._data_information = {}                             # key: [most recent access time, line number]
        self._set_fullness = [0] * n                            # number of elements currently in each set
        self._sets = [[None] * self._lines_per_set] * n           # the sets themselves, arrays with l lines, there are n of them



        self._condition = threading.Condition()
        self._jobs_queue = ThreadNotifierFIFOList(self._condition)
        self._job_finished = threading.Barrier(self._number_of_sets)
        self._read_write_lock = threading.Lock()

        # Creating dedicated threads for reading/writing to each set
        self._create_threads()



    def _set_replacement_algorithm(self, replacement_algorithm):

        # Checking for custom replacement algorithm
        if callable(replacement_algorithm):
            self._replacement_algorithm = replacement_algorithm
            return True

        # Checking for one of the preset replacement algorithms
        elif replacement_algorithm.isalpha():
            replacement_algorithm = replacement_algorithm.upper()
            if replacement_algorithm == "LRU":
                self._replacement_algorithm = self._lru
                return True
            elif replacement_algorithm == "MRU":
                self._replacement_algorithm = self._mru
                return True

        # If we reach the end then no valid replacement algorithm was given
        return False

    def _create_threads(self):
        for i in range(self._number_of_sets):
            worker_thread = threading.Thread(target=self._worker, args=(i,))
            worker_thread.daemon = True
            worker_thread.start()

    def _worker(self, worker_thread_id):  # worker_thread_id corresponds with a set that this thread will always work on
        while True:

            with self._condition:
                if self._jobs_queue.is_empty():
                    self._condition.wait()

            current_job = self._jobs_queue.peek()

            if current_job is None:
                continue

            self._read_write_lock.acquire()

            if current_job is self._jobs_queue.peek():

                print('thread: ', worker_thread_id, 'executing: ', current_job)
                # update required fields
                # time.time() ## to get the current time for comparisons

                self._jobs_queue.pop()

            self._read_write_lock.release()

            self._job_finished.wait()

    def _lru(self, current_set):
        """
        :param current_set: a full set
        :return: the index of the least recently used element within this set
        """
        pass

    def _mru(self, current_set):
        """
        :param current_set: a full set
        :return: the index of the most recently used element within this set
        """
        pass

    def put(self, key, value):
        if key not in self._data_information:
            self._jobs_queue.append(WorkerJob(CacheAction.ADD, (key, value)))
        else:
            self._jobs_queue.append(WorkerJob(CacheAction.UPDATE, (key, value)))

    def get(self, key):
        self._jobs_queue.append(WorkerJob(CacheAction.GET, key))
        # TODO:wait for thread response and then return the correct data, I can probably use a threading.Event for this.


if __name__ == '__main__':
    test_cache = NWaySetAssociativeCache()
    test_cache.put(1, 1)
    test_cache.put(2, 2)
    test_cache.put(3, 3)
    time.sleep(2)


































### HARD TIME


#
# if current_job.job_type is CacheAction.ADD:
#     print("ADD")
#
#     # find position
#     # possibly involve the replacement algorithm
#
#     self._read_write_lock.acquire()
#
#     if current_job is self._jobs_queue.peek():
#         # update required fields
#
#         self._jobs_queue.pop()
#
#     self._read_write_lock.release()
#
#     # release lock
#
# elif current_job.job_type is CacheAction.UPDATE:
#
#     # search expected position
#
#
#     self._read_write_lock.acquire()
#
#     if current_job is self._jobs_queue.peek():
#         # update required fields
#
#         self._jobs_queue.pop()
#
#     self._read_write_lock.release()
#
#     # if we find the correct value
#
#     # updated required fields
#
#     # pop the job
#
# else:  # CacheAction.GET
#     pass





















#### DEATH ROW


# class FinishedEvent(threading.Event):
#
#     def __init__(self, _n):
#         super().__init__()
#         self._n = _n
#         self._count = 0
#
#     def set(self):
#         self._count += 1
#         if self._count == self._n:
#             with self._cond:
#                 self._flag = True
#                 self._cond.notify_all()
#
#     def clear(self):
#         with self._cond:
#             self._flag = False
#             self._count = 0











# def worker():
#     # read in value from the jobs queue
#     # test if it is an update or not
#
#     # if not update, find next index to remove (if set is full fidn index based on replacement algorithm)
#     # if update, then find the current position of the element and update accordingly (will only be in 1 set)
#             # issue: how do I differentiate the data on the same line of one set as another if keys are kept external ????
#
#             # a way around this: store the key with the value, so we will know what position the key is in
#             # and then when we check we only take the line where the key matches
#
#
#
#     # once i know which line to alter then I enter a thread safe region where the data is actually updated
#
#     # a note on races: we want to reduce the number of misses so we should only actually do replacement if there definitely
#     # isn't an available spot in one of the four sets, so there should be a check before doing this
#         # i don't think this is necessary actually, because we can just use the first to get placing it in alwyas
#
#     # on add: all threads race to get to this position and the first is the one that adds into it's corresponding set
#
#     #  on update: when a thread gets to this position it should only have an index to replace if it is the correct set,
#         # the other sets should have None and then exit gracefully
#         # this is where the issue will occur since multiple threads may have information on this line
#
#     print('In thread')



#
#
#
# def worker(condition, jobs_queue):
#     while True:
#
#         with condition:
#             if l.is_empty():
#                 condition.wait()
#
#             print("worker has woken: ", threading.get_ident())
#             time.sleep(0.001)
#
#             # do work
#
#             # need to have critical sections associated with popping and doing the actual updates to the class variables
#                 # time.time() ## to get the current time for comparisons
#
#             l.pop()
