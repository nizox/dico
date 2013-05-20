from collections import MutableSequence, MutableMapping


class NotifyList(MutableSequence):

    def __init__(self, *args, **kwargs):
        super(NotifyList, self).__init__()
        self._parents = set()
        self._list = list(*args, **kwargs)

    def __getitem__(self, index):
        return list.__getitem__(self._list, index)

    def __setitem__(self, index, value):
        # TODO this test is not precise
        if hasattr(value, "_parents"):
            value._parents = value._parents.union(self._parents)
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        self._list[index] = value

    def __delitem__(self, index):
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        del self._list[index]

    def insert(self, index, value):
        if hasattr(value, "_parents"):
            value._parents = value._parents.union(self._parents)
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        return self._list.insert(index, value)

    def __len__(self):
        return len(self._list)


class NotifyDict(MutableMapping):

    def __init__(self, *args, **kwargs):
        super(NotifyDict, self).__init__()
        self._parents = set()
        self._dict = dict(*args, **kwargs)

    def __getitem__(self, index):
        return dict.__getitem__(self._dict, index)

    def __setitem__(self, index, value):
        if hasattr(value, "_parents"):
            value._parents = value._parents.union(self._parents)
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        self._dict[index] = value

    def __delitem__(self, index):
        for parent, parent_fields in self._parents:
            parent_fields._changed(parent)
        del self._dict[index]

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)
