from itertools import chain

def words_from_name(wire, pad=False):
    words = wire.split('_')
    if pad:
        return chain([None], words, [None])
    else:
        return words
