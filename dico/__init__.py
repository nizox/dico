import re
import datetime
import socket
import operator

URL_REGEX_COMPILED = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)

EMAIL_REGEX_COMPILED = re.compile(
    # dot-atom
    r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"
    # quoted-string
    r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-011\013\014\016'
    r'-\177])*"'
    # domain
    r')@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?$',
    re.IGNORECASE
)


class ValidationException(Exception):
    """The field did not pass validation.
    """
    pass


class BaseField(object):
    def __init__(self, default=None, required=False, choices=None):
        """ the BaseField class for all Document's field
        """
        self.default = default
        self.is_required = required
        self.choices = choices

    def _register_document(self, document, field_name):
        self.field_name = field_name

    def _changed(self, instance):
        """ notify parent's document for changes """
        instance._modified_fields.add(self.field_name)
        instance._is_valid = False
        # called recursively
        if instance._parent:
            field = instance._parent_field
            field._changed(instance._parent)


class EmbeddedDocumentField(BaseField):
    def __init__(self, field_type, **kwargs):
        self.field_type = field_type

        if not isinstance(field_type, DocumentMetaClass):
            raise AttributeError('EmbeddedDocumentField only accepts Document subclass')

        super(EmbeddedDocumentField, self).__init__(**kwargs)

    def _prepare(self, instance, value, source="dict"):
        """ we instantiate the dict to an object if needed
            and set the parent
        """
        if isinstance(value, dict):
            value = getattr(self.field_type, "from_%s" % source)(**value)
            value._parent = instance
            value._parent_field = self
        if isinstance(value, self.field_type):
            value._parent_field = self
        return value

    def _validate(self, value):
        if not isinstance(value, self.field_type):
            return False

        return value.validate()


class NotifyParentList(list):
    """
        A minimal list subclass that will notify for modification to the parent
        for special case like parent.obj.append
    """
    def __init__(self, seq=(), parent=None, field=None):
        self._parent = parent
        self._field = field
        super(NotifyParentList, self).__init__(seq)

    def _tag_obj_for_parent_name(self, obj):
        """ check if the obj is a document and set his parent_name
        """
        if isinstance(obj, Document):
            obj._parent = self._parent
            obj._parent_field = self._field
            return
        try:
            iter(obj)
        except TypeError:
            return
        for entry in obj:
            if isinstance(entry, Document):
                entry._parent = self._parent
                entry._parent_field = self._field

    def _notify_parents(self):
        self._field._changed(self._parent)

    def __add__(self, other):
        self._tag_obj_for_parent_name(other)
        self._notify_parents()
        return super(NotifyParentList, self).__add__(other)

    def __setslice__(self, i, j, seq):
        self._tag_obj_for_parent_name(seq)
        self._notify_parents()
        return super(NotifyParentList, self).__setslice__(i, j, seq)

    def __delslice__(self, i, j):
        self._notify_parents()
        return super(NotifyParentList, self).__delslice__(i, j)

    def __setitem__(self, key, value):
        self._tag_obj_for_parent_name(value)
        self._notify_parents()
        return super(NotifyParentList, self).__setitem__(key, value)

    def __delitem__(self, key):
        self._notify_parents()
        return super(NotifyParentList, self).__delitem__(key)

    def append(self, p_object):
        self._tag_obj_for_parent_name(p_object)
        self._notify_parents()
        return super(NotifyParentList, self).append(p_object)

    def remove(self, value):
        self._notify_parents()
        return super(NotifyParentList, self).remove(value)

    def insert(self, index, p_object):
        self._tag_obj_for_parent_name(p_object)
        self._notify_parents()
        return super(NotifyParentList, self).insert(index, p_object)

    def extend(self, iterable):
        self._tag_obj_for_parent_name(iterable)
        self._notify_parents()
        return super(NotifyParentList, self).extend(iterable)

    def pop(self, index=None):
        if index is None:
            if super(NotifyParentList, self).pop():
                self._notify_parents()
        else:
            if super(NotifyParentList, self).pop(index):
                self._notify_parents()


class ListField(BaseField):
    def __init__(self, subfield, max_length=0, min_length=0, **kwargs):
        self.subfield = subfield
        self.max_length = max_length
        self.min_length = min_length
        if "default" not in kwargs:
            kwargs["default"] = []

        if not isinstance(subfield, (BaseField)):
            raise AttributeError('ListField only accepts BaseField subclass')

        super(ListField, self).__init__(**kwargs)

    def _register_document(self, document, field_name):
        self.subfield._register_document(document, field_name)
        BaseField._register_document(self, document, field_name)

    def _validate(self, value):
        if not isinstance(value, list):
            return False
        if self.max_length != 0:
            if len(value) > self.max_length:
                return False
        if self.min_length != 0:
            if len(value) < self.min_length:
                return False
        for entry in value:
            if not self.subfield._validate(entry):
                return False
        return True

    def _prepare(self, instance, value, source="dict"):
        """ we set the parent for each element
            and set a NotifyParentList in place of a list
        """
        try:
            iter(value)
        except TypeError:
            pass
        else:
            if hasattr(self.subfield, "_prepare"):
                obj_list = []
                for obj in value:
                    obj = self.subfield._prepare(instance, obj, source=source)
                    if obj:
                        obj_list.append(obj)
                value = obj_list
            if not isinstance(value, NotifyParentList):
                value = NotifyParentList(value, parent=instance, field=self)
        return value


class BooleanField(BaseField):
    def _validate(self, value):
        if not isinstance(value, (bool)):
            return False
        return True


class StringField(BaseField):
    def __init__(self, compiled_regex=None, max_length=None, min_length=None, **kwargs):
        self.compiled_regex = compiled_regex
        self.max_length = max_length
        self.min_length = min_length
        super(StringField, self).__init__(**kwargs)

    def _validate(self, value):
        if not isinstance(value, (str, unicode)):
            return False

        if self.max_length is not None and len(value) > self.max_length:
            return False

        if self.min_length is not None and len(value) < self.min_length:
            return False

        if self.compiled_regex is not None and self.compiled_regex.match(value) is None:
            if value == '' and not self.is_required:
                return True
            return False

        return True


class IPAddressField(StringField):
    """ validate ipv4 and ipv6
    """
    def _validate(self, value):
        try:
            socket.inet_pton(socket.AF_INET, value)
        except socket.error:
            try:
                socket.inet_pton(socket.AF_INET6, value)
            except socket.error:
                return False
        return True


class URLField(StringField):
    def __init__(self, **kwargs):
        super(URLField, self).__init__(compiled_regex=URL_REGEX_COMPILED, **kwargs)


class EmailField(StringField):
    def __init__(self, **kwargs):
        super(EmailField, self).__init__(compiled_regex=EMAIL_REGEX_COMPILED, **kwargs)


class IntegerField(BaseField):
    def _validate(self, value):
        if not isinstance(value, (int, long)):
            return False
        return True


class FloatField(BaseField):
    def _validate(self, value):
        if not isinstance(value, (float, int)):
            return False
        return True


class DateTimeField(BaseField):
    def _validate(self, value):
        if not isinstance(value, (datetime.datetime)):
            return False
        return True


class DocumentMetaClass(type):
    def __new__(cls, name, bases, attrs):
        meta = attrs.get("_meta", False)
        if not meta:
            fields = {}
            newattrs = {}
            for attr_name, attr_value in attrs.items():
                if isinstance(attr_value, BaseField):
                    fields[attr_name] = attr_value
                else:
                    newattrs[attr_name] = attr_value
            newattrs["__slots__"] = tuple(fields.keys())
            newattrs["_fields"] = fields
        else:
            newattrs = attrs
        newattrs["_meta"] = meta

        klass = type.__new__(cls, name, bases, newattrs)

        if not meta:
            for field_name, field in klass._fields.items():
                field._register_document(klass, field_name)

            for base in bases:
                if not getattr(base, "_meta", True):
                    base_fields = base._fields.copy()
                    base_fields.update(klass._fields)
                    klass._fields = base_fields

            klass.add_source("dict")
            klass.add_view("dict")
        return klass


class Document(object):

    __metaclass__ = DocumentMetaClass
    __slots__ = ('_modified_fields', '_is_valid', '_parent', '_parent_field')

    _meta = True

    def __init__(self, **values):
        self._modified_fields = set()
        # optimization to avoid double validate() if nothing has changed
        self._is_valid = False
        self._parent = None
        self._parent_field = None

        self.update_from_dict(values, changed=False)

    def __getattr__(self, name):
        field = self._fields.get(name)
        if field:
            value = field.default
            if callable(value):
                value = value()
            if value is not None:
                if hasattr(field, "_prepare"):
                    value = field._prepare(self, value)
                object.__setattr__(self, name, value)
            return value
        raise AttributeError

    def __setattr__(self, name, value):
        field = self._fields.get(name)
        if field is not None:
            if hasattr(field, "_prepare"):
                value = field._prepare(self, value)
            field._changed(self)
        return object.__setattr__(self, name, value)

    def _validate_fields(self, fields_list, stop_on_required=True):
        """ take a list of fields name and validate them
            return True if all fields in fields_list required are valid and set
            return True if fields in fields_list are valid
            and set if stop_on_required=False
        """
        for field_name in fields_list:
            # if field name is not in the field list but a property
            if field_name not in self._fields.keys():

                if hasattr(self, field_name):
                    continue
                else:
                    raise KeyError

            field = self._fields[field_name]
            value = getattr(self, field_name, None)

            if value is None:
                if stop_on_required and field.is_required:
                    return False
                continue

            # validate possible choices first
            if field.choices is not None:
                if value not in field.choices:
                    return False

            if not field._validate(value):
                return False

        return True

    def validate(self, stop_on_required=True):
        """ return True if all required are valid and set
            return True if fields are valid and set if required=False
            see validate_partial
        """
        if stop_on_required and self._is_valid:
            return True

        is_valid = self._validate_fields(self._fields.keys(),
            stop_on_required=stop_on_required)

        if stop_on_required and is_valid:
            self._is_valid = True

        return is_valid

    def validate_partial(self):
        """ validate only the format of each field regardless of stop_on_required option
            usefull to validate some parts of a document
        """
        return self.validate(stop_on_required=False)

    def modified_fields(self):
        """ return a set of fields modified via setters
        """
        return self._modified_fields

    @classmethod
    def add_source(cls, name, keep_fields=None, remove_fields=None,
            filter=None):
        """Add new import methods to the document. The import methods may be
        specialized according to the arguments *keep_fields*, *remove_fields*
        and *filter*.

        By default every document is created with a **dict** source providing
        the method ``update_from_dict`` and the class method ``from_dict``.
        """

        if keep_fields is not None:
            fields = [(x, cls._fields.get(x)) for x in keep_fields]
        elif remove_fields is not None:
            fields = [(name, field) for name, field in cls._fields
                    if name not in remove_fields]
        else:
            fields = cls._fields.items()

        def update(self, data, changed=True):
            if callable(filter):
                data = filter(data)
            elif isinstance(filter, basestring):
                data = getattr(self, filter)(data)

            for key, field in fields:
                value = data.get(key)

                if value is not None:
                    if hasattr(field, "_prepare"):
                        value = field._prepare(self, value,
                                source=name)
                    object.__setattr__(self, key, value)
                    if changed:
                        field._changed(self)
            return self

        update.__name__ = "update_from_%s" % name
        update.__doc__ = """
        Update a document from a Python ``dict``.
        """
        updategetter = operator.attrgetter(update.__name__)

        def source(cls, **kwargs):
            instance = cls()
            return updategetter(instance)(kwargs, changed=False)

        source.__name__ = "from_%s" % name
        source.__doc__ = """
        Create a document from Python keyword arguments.
        """

        setattr(cls, "%s_source_fields" % name, tuple([x[0] for x in fields]))
        setattr(cls, update.__name__, update)
        setattr(cls, source.__name__, classmethod(source))

    @classmethod
    def add_view(cls, name, keep_fields=None, remove_fields=None,
            filter=None):
        """Add new export methods to the document. The export methods may be
        specialized according to the arguments *keep_fields*, *remove_fields*
        and *filter*.

        By default every document is created with a **dict** view providing
        the method ``to_dict``."""

        if keep_fields is not None:
            fields = keep_fields
        elif remove_fields is not None:
            fields = [field for field in cls._fields.keys()
                    if field not in remove_fields]
        else:
            fields = cls._fields.keys()

        todo = []
        methodcaller = operator.methodcaller("to_%s" % name)
        for field_name in fields:
            field = cls._fields.get(field_name)

            if isinstance(field, EmbeddedDocumentField):
                todo.append((field_name, methodcaller))
            elif isinstance(field, ListField) and \
                    isinstance(field.subfield, EmbeddedDocumentField):

                def loopcaller(value):
                    new_value = []
                    for elem in value:
                        new_value.append(methodcaller(elem))
                    return new_value

                todo.append((field_name,
                    loopcaller))
            else:
                todo.append((field_name, None))

        def view(self, only_modified=False, validate=True):
            if validate and not self.validate():
                raise ValidationException

            if only_modified:
                todo_specialized = [(key, do) for key, do in todo
                        if key in self.modified_fields()]
            else:
                todo_specialized = todo

            data = {}
            for key, do in todo_specialized:
                value = getattr(self, key)
                if value is not None:
                    if do:
                        value = do(value)
                    data[key] = value
            if callable(filter):
                data = filter(data)
            elif isinstance(filter, basestring):
                data = getattr(self, filter)(data)
            return data

        view.__name__ = "to_%s" % name
        view.__doc__ = """Export the document to a Python dict."""

        setattr(cls, "%s_view_fields" % name, tuple(fields))
        setattr(cls, view.__name__, view)


def rename_field(old_name, new_name):
    """Make a filter renaming *old_name* to *new_name*."""
    def _rename_field(data):
        elem = data.pop(old_name, None)
        if elem is not None:
            data[new_name] = elem
        return data
    return _rename_field


def format_field(name, func):
    """Make a filter replacing the content of the field *name* by the result of
    the function *func*."""
    def _format_field(data):
        elem = data.get(name)
        if elem is not None:
            data[name] = func(elem)
        return data
    return _format_field
