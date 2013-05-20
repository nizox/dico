from collections import MutableSequence


class NotifyList(MutableSequence):

    def __init__(self, *args, **kwargs):
        super(NotifyList, self).__init__()
        self._parents = set()
        self._list = list(*args, **kwargs)

    def __len__(self):
        return list.__len__(self._list)

    def __getitem__(self, index):
        return list.__getitem__(self._list, index)

    def __setitem__(self, index, value):
        try:
            seq = iter(value)
        except TypeError:
            seq = [value]
        for entry in seq:
            # TODO this test is not precise
            if hasattr(entry, "_parents"):
                entry._parents = entry._parents.union(self._parents)
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        self._list[index] = value

    def __delitem__(self, index):
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        del self._list[index]

    def insert(self, index, value):
        try:
            seq = iter(value)
        except TypeError:
            seq = [value]
        for entry in seq:
            # TODO this test is not precise
            if hasattr(entry, "_parents"):
                entry._parents = entry._parents.union(self._parents)
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        return self._list.insert(index, value)
