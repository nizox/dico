try:
    import bson.objectid
except ImportError:
    raise ImportError("Using the ObjectIdField requires Pymongo.")

from . import BaseField, ListField, FloatField


class ObjectIdField(BaseField):
    def _validate(self, value):
        if not isinstance(value, (bson.objectid.ObjectId)):
            return False
        return True


class GeoPointField(ListField):
    def __init__(self, **kwargs):
        super(GeoPointField, self).__init__(FloatField(),
                min_length=2, max_length=2, **kwargs)
