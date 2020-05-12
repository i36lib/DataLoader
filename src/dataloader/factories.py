import uuid
import time
import random
import numpy as np
import numpy.random
import factory.fuzzy

rng = np.random.default_rng()


def random_int(size):
    return int(time.time() % size) + 1


class FuzzyUuid(factory.fuzzy.BaseFuzzyAttribute):
    def __init__(self, as_str=True):
        super(FuzzyUuid, self).__init__()
        self._as_str = as_str

    def fuzz(self):
        u = uuid.uuid4()
        if self._as_str:
            u = str(u)
        return u


class FuzzyText(factory.fuzzy.BaseFuzzyAttribute):
    def __init__(self, sz=16):
        super(FuzzyText, self).__init__()
        self.sz = 16 if sz <= 0 else sz

    def fuzz(self):
        s, e = (97, 123)  # a ~ z
        seed = rng.integers(s, e, size=(1, min(16, self.sz)), dtype=np.int8)
        return ''.join([chr(x) for x in seed[0]])


class FuzzyBoolean(factory.fuzzy.BaseFuzzyAttribute):
    def __init__(self, as_str=False):
        super(FuzzyBoolean, self).__init__()
        self._as_str = as_str

    def fuzz(self):
        return random.choice([True, False])


class FuzzyMultiChoices(factory.fuzzy.BaseFuzzyAttribute):
    def __init__(self, sample, number=None, **kwargs):
        super(FuzzyMultiChoices, self).__init__()
        self._sample = sample
        self._k = number
        self._sample_len = len(sample)

    def fuzz(self):
        return set(random.sample(
            self._sample,
            k=self._k or random_int(self._sample_len)
        ))


class FuzzyFasterChoice(FuzzyMultiChoices):
    def __init__(self, sample, number=1, **kwargs):
        super(FuzzyMultiChoices, self).__init__()
        self._sample = sample
        self._k = number
        self._sample_len = len(sample)
