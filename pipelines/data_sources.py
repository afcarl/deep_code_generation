from lazychef.data_sources import Datasource, LambdaDatasource
from huzzer.huzz import huzzer
from huzzer.tokenizing import tokenize
from random import Random
import numpy as np
import logging


BASIC_DATASET_ARGS = {
    'max_expression_depth': 3,
    'max_type_signiature_length': 2,
    'max_number_of_functions': 2
}


class HuzzerSource(Datasource):
    def __init__(self, huzzer_kwargs={}):
        self.huzzer_kwargs = huzzer_kwargs

    def _process(self, ident):
        assert ident.isdigit(), 'huzzer got {}, when it should take a number'.format(ident)
        return huzzer(int(ident), **self.huzzer_kwargs)


class CharSplitter(Datasource):
    """
    Take some code, and pick a random character for the proceeding character. Returns all code up to that character.
    The characters are all reaturned in one string, i.e. the final character of the string is the target value.

    Takes urls as '<code_seed>/<splitting_seed>' where both seeds are integers.
    """

    def __init__(self, code_ds):
        self.data_source = code_ds
        self.rand = Random()

    def _process(self, ident):
        seeds = ident.split('/')
        assert len(seeds) == 2, 'Got {} instead of <code_seed>,<splitting_seed>'.format(seeds)

        code_seed, splitting_seed = seeds

        assert code_seed.isdigit(), \
            'CharSplitter got {} for code_seed, when it should take a number'.format(code_seed)
        assert splitting_seed.isdigit(), \
            'CharSplitter got {} for splitting_seed, when it should take a number'.format(splitting_seed)

        code = self.data_source[code_seed]

        # split code deteministically
        self.rand.seed(int(splitting_seed))
        result_char_idx = self.rand.randint(0, len(code)-1)

        prior_string = code[:result_char_idx]
        return prior_string + code[result_char_idx]


def OneHotVecotorizerASCII(split_ds, total_string_length=33):
    """
    Take ascii strings from a CharSplitter like Datasource and turns the chars into one-hot vectors of length 128.
    """
    def one_hoterize(data):
        nonlocal total_string_length  # NOQA
        data = data[-total_string_length:]
        for x in data:
            assert ord(x) < 128, 'character {} in {} is not ascii'.format(x, data)

        one_hots = np.zeros((len(data), 128), np.uint8)
        one_hots[np.arange(len(data)), [ord(c) for c in data]] = 1

        # add padding
        if one_hots.shape[0] != total_string_length:
            padding_to_add = total_string_length - one_hots.shape[0]
            padding = np.zeros((padding_to_add, 128), np.uint8)
            one_hots = np.concatenate((padding, one_hots))

        assert one_hots.shape == (total_string_length, 128)
        return one_hots

    return LambdaDatasource(split_ds, one_hoterize)


def vec_to_char(vec):
    return chr(np.nonzero(vec)[0][0])


class TokenDatasource(Datasource):
    def __init__(self, huzz_ds: HuzzerSource):
        self.huzz_ds = huzz_ds

    def _process(self, key):
        code = self.huzz_ds[key]
        return [x.type for x in tokenize(code) if x.channel == 0]


class OneHotVecotorizer(Datasource):
    """
    Get a source of tokens of `alphabet_size` sized alphabet. Turn it into
    one hot vectors. If length_cap is specified, then vectors are padded with
    empty vectors, and sentences generated longer or equal to `length_cap` cause the
    Datasource to get a deteministically random 'other' key.

    If `max_len` is None, a single empty vector is added to the end to represent
    an end token
    """
    def __init__(self, ds, alphabet_size, length_cap=None):
        self.ds = ds
        self.alphabet_size = alphabet_size
        self.length_cap = length_cap
        self.rand = Random()

    def _process(self, key):
        sentence = self.ds[key]
        if self.length_cap is not None and len(sentence) >= self.length_cap:
            self.rand.seed(int(key))
            new_key = self.rand.randint(0, 2**30)
            logging.debug('{} is too long!, getting {}'.format(key, new_key))
            return self[str(new_key)]

        # final token needs to be a 'finish' token
        array_len = self.length_cap if self.length_cap is not None else (len(sentence) + 1)
        arr = np.zeros((array_len, self.alphabet_size), dtype=np.uint8)
        arr[range(len(sentence)), sentence] = 1

        # all tokens range from 1->53. a zero value represents `nothing`. i.e. padding/end characters
        arr[range(len(sentence), len(arr)), 0] = 1
        return arr
