
import threading
from enum import Enum


class CacheAction(Enum):
    PUT = 0
    GET = 1


class ThreadNotifierFIFOQueue(object):
    """
    A FIFO Queue that notifies the given condition when it is added to.
    This will awaken the waiting threads such that they may process incoming jobs.
    """

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

        with self._condition:
            self._condition.notify_all()         # all of the threads will awaken

        if self._head is None:
            self._head = ThreadNotifierFIFOQueue.ListNode(item)
            self._tail = self._head
        else:
            self._tail.next = ThreadNotifierFIFOQueue.ListNode(item)
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


class JobData(object):
    """
    The information passed to the GET or PUT requests.
    """

    def __init__(self, key, data=None):
        self.key = key
        self.data = data

    def __repr__(self):
        return str(self.key) + " - " + str(self.data)


class WorkerJob(object):
    """
    Jobs that are processed by the n worker threads created by the cache.
    """

    def __init__(self, job_type, job_data):
        self.job_type = job_type
        self.job_data = job_data

    def __repr__(self):
        return str(self.job_type) + " - " + str(self.job_data)


class CacheData(object):
    """
    An object used to store data within the cache.
    next and prev are used to retain the ordering of when each item was most recently used.
    """

    def __init__(self, key, data, next_item):
        self.key = key
        self.data = data
        self.next = next_item        # object used immediately less recently than this object
        self.prev = None             # object used immediately more recently than this object

    def __repr__(self):
        return str(self.key) + " - " + str(self.data)


class NWaySetAssociativeCache(object):

    def __init__(self, n=4, replacement_algorithm="LRU", lines=32):
        """
        Initializes cache private members and starts dedicated read/write threads for each set.
        :param n: the number of sets in the cache
        :param replacement_algorithm: either LRU, MRU, or a custom static replacement algorithm
        :param lines: the number of items that can fit within one set
        """

        # Setting the replacement algorithm (Either LRU, MRU, or user-defined)
        self._replacement_algorithm = None
        if not self._set_replacement_algorithm(replacement_algorithm):
            raise ValueError("Replacement algorithm parameter must designate LRU or MRU or be a function.")

        self._number_of_sets = n
        self._lines_per_set = lines

        # Data storage and retrieval
        self._keys = set()
        self._sets = [{} for i in range(n)]
        self.data_head = [None] * n
        self.data_tail = [None] * n

        # Jobs parallelization objects
        self._new_job_condition = threading.Condition()
        self._jobs_queue = ThreadNotifierFIFOQueue(self._new_job_condition)
        self._job_finished = threading.Barrier(self._number_of_sets)
        self._write_lock = threading.Lock()
        self._get_condition = threading.Condition()

        # Used for returning data from get requests
        self._get_data_set_index = None

        # Creating dedicated threads for reading/writing to each set
        self._create_threads()

    def _set_replacement_algorithm(self, replacement_algorithm):
        """
        Determines and sets the replacement algorithm class variable.
        :param replacement_algorithm: either LRU, MRU, or a custom static method
        :return: True if successful, False otherwise
        """

        # Checking for custom replacement algorithm
        if callable(replacement_algorithm):
            self._replacement_algorithm = replacement_algorithm
            return True

        # Checking for one of the preset replacement algorithms
        elif isinstance(replacement_algorithm, str):
            replacement_algorithm = replacement_algorithm.upper()
            if replacement_algorithm == "LRU":
                self._replacement_algorithm = self.lru
                return True
            elif replacement_algorithm == "MRU":
                self._replacement_algorithm = self.mru
                return True

        # If we reach the end then no valid replacement algorithm was given
        return False

    def _create_threads(self):
        """
        Begins n daemon threads which will remain active waiting for jobs.
        """
        for i in range(self._number_of_sets):
            worker_thread = threading.Thread(target=self._worker, args=(i,))
            worker_thread.daemon = True
            worker_thread.start()

    def _update_ordering(self, current_item, worker_thread_id):
        """
        Preserves the ordering of recent use assuming that current_item is currently being moved.
        An item can only either be moved to the head or removed entirely.
        :param current_item: the item being updated/removed
        :param worker_thread_id: the thread ID corresponding to the set that this item exists within
        """
        if current_item.prev:
            current_item.prev.next = current_item.next

        if current_item is self.data_tail[worker_thread_id]:
            self.data_tail[worker_thread_id] = current_item.prev
        else:
            current_item.next.prev = current_item.prev

    def _worker(self, worker_thread_id):
        """
        This function loops continuously, waiting for new jobs and then processing the requests.
        Jobs may be either PUT or GET jobs. Each thread is given an ID such that it will work on
        the same set throughout it's lifetime.
        :param worker_thread_id: the thread ID corresponding to the set that it will act on
        """

        # worker_thread_id corresponds with a set that this thread will always work on
        worker_set = self._sets[worker_thread_id]
        while True:

            # Waiting and acquiring new job when queue is not empty
            with self._new_job_condition:
                if self._jobs_queue.is_empty():
                    self._new_job_condition.wait()
            current_job = self._jobs_queue.peek()

            if current_job is not None:

                # Inserting new data
                if current_job.job_data.key not in self._keys and current_job.job_type == CacheAction.PUT:

                    # Determine if/which resource needs to be removed
                    remove_key = None
                    if len(worker_set) == self._lines_per_set:
                        remove_key = self._replacement_algorithm(self, worker_thread_id)

                    # Critical section, only allow changes to the cache if the job still exists
                    # Job will be removed from queue before the end of the thread safe critical section
                    self._write_lock.acquire()

                    if current_job is self._jobs_queue.peek():

                        # If a removal is necessary to maintain cache size
                        if remove_key:
                            self._update_ordering(worker_set.pop(remove_key), worker_thread_id)
                            self._keys.remove(remove_key)

                        worker_set[current_job.job_data.key] = CacheData(current_job.job_data.key, current_job.job_data.data, self.data_head[worker_thread_id])

                        # Updating relative ordering of set members
                        if self.data_head[worker_thread_id]:
                            self.data_head[worker_thread_id].prev = worker_set[current_job.job_data.key]
                        self.data_head[worker_thread_id] = worker_set[current_job.job_data.key]

                        self._keys.add(current_job.job_data.key)

                        if self.data_tail[worker_thread_id] is None:
                            self.data_tail[worker_thread_id] = worker_set[current_job.job_data.key]

                        # The job has been completed
                        self._jobs_queue.pop()

                    self._write_lock.release()

                # Accessing/updating existing data
                else:

                    # If the key has been removed from the data set between job received and job processed
                    if current_job.job_data.key not in self._keys:

                        # Ensuring only one thread acts per job
                        if current_job is self._jobs_queue.peek():

                            self._write_lock.acquire()

                            self._get_data_set_index = None
                            with self._get_condition:
                                self._get_condition.notify_all()

                            self._jobs_queue.pop()

                            self._write_lock.release()

                    else:
                        # Exactly one thread can act for a get/update job
                        if current_job.job_data.key in worker_set:

                            current_item = worker_set[current_job.job_data.key]

                            if current_job.job_type == CacheAction.GET:

                                # Temporarily store set index to be used by main thread
                                self._get_data_set_index = worker_thread_id
                                with self._get_condition:
                                    self._get_condition.notify_all()

                            else:

                                current_item.data = current_job.job_data.data

                            if current_item is not self.data_head[worker_thread_id]:

                                # Updating linked list for keeping track of recent access within the cache
                                self._update_ordering(current_item, worker_thread_id)
                                current_item.prev = None
                                current_item.next = self.data_head[worker_thread_id]

                                if self.data_head[worker_thread_id]:
                                    self.data_head[worker_thread_id].prev = worker_set[current_job.job_data.key]

                                self.data_head[worker_thread_id] = current_item

                            # The job has been completed
                            self._jobs_queue.pop()

            # Barrier to ensure that all threads finish the loop at the same time
            # This prevents a single thread from taking all of the jobs
            self._job_finished.wait()

    @staticmethod
    def lru(class_instance, current_set_id):
        """
        Determines and returns the least recently used item within the indicated set.
        :param class_instance: a pointer to the cache object
        :param current_set_id: the set of which we are looking for the LRU
        :return: the object corresponding to the least recently used entry of the set
        """
        return class_instance.data_tail[current_set_id].key

    @staticmethod
    def mru(class_instance, current_set_id):
        """
        Determines and returns the most recently used item within the indicated set.
        :param class_instance: a pointer to the cache object
        :param current_set_id: the set of which we are looking for the MRU
        :return: the object corresponding to the most recently used entry of the set
        """
        return class_instance.data_head[current_set_id].key

    def put(self, key, data):
        """
        Inserts data into the cache, identifiable by key. If there is a resource within the cache
        already bound to key, this data is replaced by the incoming data.
        :param key: any value used to identify the data
        :param data: any resource
        """
        self._jobs_queue.append(WorkerJob(CacheAction.PUT, JobData(key, data)))

    def get(self, key):
        """
        Returns the data associated with the given key in the cache if it exists.
        :param key: any key
        :return: the corresponding data associated with the key within the cache
        :raises: ValueError if the key is not present within the cache
        """

        self._jobs_queue.append(WorkerJob(CacheAction.GET, JobData(key)))

        with self._get_condition:
            self._get_condition.wait()

        if self._get_data_set_index is None:
            raise ValueError("Specified key is not present in cache.")
        else:
            return self._sets[self._get_data_set_index][key].data
