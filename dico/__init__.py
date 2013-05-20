import re
import datetime
import socket
import operator

from .mutable import NotifyList, MutableSequence, NotifyDict, MutableMapping

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
        for parent, parent_field in instance._parents:
            parent_field._changed(parent)


class EmbeddedDocumentField(BaseField):
    def __init__(self, field_type, **kwargs):
        self.field_type = field_type

        if not isinstance(field_type, DocumentMetaClass):
            raise AttributeError('EmbeddedDocumentField only accepts Document subclass')

        super(EmbeddedDocumentField, self).__init__(**kwargs)

    def _prepare(self, instance, value, source=None):
        """ we instantiate the dict to an object if needed
            and set the parent
        """
        if isinstance(value, dict):
            if source is None:
                source = "dict"
            value = getattr(self.field_type, "from_%s" % source,
                    self.field_type.from_dict)(**value)
        # we should not fail if value has the wrong type
        if isinstance(value, self.field_type):
            value._parents.add((instance, self))
        return value

    def _validate(self, value):
        if not isinstance(value, self.field_type):
            return False

        return value.validate()


class MappingField(BaseField):
    def __init__(self, keysubfield, valuesubfield, **kwargs):
        self.keysubfield = keysubfield
        self.valuesubfield = valuesubfield
        if "default" not in kwargs:
            kwargs["default"] = {}

        if not isinstance(keysubfield, BaseField) \
                or not isinstance(valuesubfield, BaseField):
            raise AttributeError('MappingField only accepts '
                'BaseField subclass')

        super(MappingField, self).__init__(**kwargs)

    def _register_document(self, document, field_name):
        self.keysubfield._register_document(document, field_name)
        self.valuesubfield._register_document(document, field_name)
        super(MappingField, self)._register_document(document, field_name)

    def _validate(self, value):
        if not isinstance(value, MutableMapping):
            return False
        for key, value in value.items():
            if not self.keysubfield._validate(key):
                return False
            if not self.valuesubfield._validate(value):
                return False
        return True

    def _prepare(self, instance, values, source=None):
        """ we set the parent for each element
            and set a NotifyParentList in place of a list
        """
        if isinstance(values, MutableMapping):
            obj_mapping = NotifyDict()
            for key, value in values.items():
                if hasattr(self.keysubfield, "_prepare"):
                    key = self.keysubfield._prepare(instance, key,
                            source=source)
                if hasattr(self.valuesubfield, "_prepare"):
                    value = self.valuesubfield._prepare(instance, value,
                            source=source)
                obj_mapping[key] = value
            obj_mapping._parents.add((instance, self))
            return obj_mapping
        return values


class ListField(BaseField):
    def __init__(self, subfield, max_length=None, min_length=None, **kwargs):
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
        if not isinstance(value, MutableSequence):
            return False
        if self.max_length is not None:
            if len(value) > self.max_length:
                return False
        if self.min_length is not None:
            if len(value) < self.min_length:
                return False
        for entry in value:
            if not self.subfield._validate(entry):
                return False
        return True

    def _prepare(self, instance, value, source=None):
        """ we set the parent for each element
            and set a NotifyParentList in place of a list
        """
        if isinstance(value, MutableSequence):
            if hasattr(self.subfield, "_prepare"):
                obj_list = NotifyList()
                for obj in value:
                    obj = self.subfield._prepare(instance, obj, source=source)
                    obj_list.append(obj)
                value = obj_list
            else:
                value = NotifyList(value)
            value._parents.add((instance, self))
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
        fields = {}
        newattrs = {}
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, BaseField):
                fields[attr_name] = attr_value
            else:
                newattrs[attr_name] = attr_value
        newattrs["_fields"] = fields

        klass = type.__new__(cls, name, bases, newattrs)

        for field_name, field in fields.items():
            field._register_document(klass, field_name)

        for base in bases:
            if hasattr(base, "_fields"):
                base_fields = base._fields.copy()
                base_fields.update(klass._fields)
                klass._fields = base_fields

        klass.add_source("dict")
        klass.add_view("dict")
        return klass


class Document(object):

    __metaclass__ = DocumentMetaClass

    def __init__(self, **values):
        self._modified_fields = set()
        # optimization to avoid double validate() if nothing has changed
        self._is_valid = False
        self._parents = set()

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
            fields = [(field_name, cls._fields.get(field_name))
                for field_name in keep_fields]
        elif remove_fields is not None:
            fields = [(field_name, field) for field_name, field in
                    cls._fields.items() if field_name not in remove_fields]
        else:
            fields = cls._fields.items()

        setattr(cls, "%s_source_fields" % name, tuple([x[0] for x in fields]))

        for _, field in fields:
            if isinstance(field, EmbeddedDocumentField):
                if not hasattr(field.field_type, "%s_source_fields" % name):
                    # create a default source for the embedded document
                    field.field_type.add_source(name)
            elif isinstance(field, ListField) and \
                    isinstance(field.subfield, EmbeddedDocumentField):

                if not hasattr(field.subfield.field_type, "%s_source_fields"
                        % name):
                    # create a default source for the embedded document
                    field.subfield.field_type.add_source(name)
            elif isinstance(field, MappingField) and \
                    isinstance(field.valuesubfield, EmbeddedDocumentField):

                if not hasattr(field.valuesubfield.field_type,
                        "%s_source_fields" % name):
                    # create a default source for the embedded document
                    field.valuesubfield.field_type.add_source(name)

        def update(self, data, changed=True):
            if callable(filter):
                data = filter(data)
            elif isinstance(filter, basestring):
                data = getattr(self, filter)(data)

            for key, field in fields:
                value = data.get(key)

                if value is not None:
                    if field is not None:
                        if hasattr(field, "_prepare"):
                            value = field._prepare(self, value,
                                    source=name)
                        object.__setattr__(self, key, value)
                        if changed:
                            field._changed(self)
                    else:
                        object.__setattr__(self, key, value)
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

        setattr(cls, "%s_view_fields" % name, tuple(fields))

        todo = []
        methodcaller = operator.methodcaller("to_%s" % name)
        for field_name in fields:
            field = cls._fields.get(field_name)

            if isinstance(field, EmbeddedDocumentField):
                if not hasattr(field.field_type, "%s_view_fields" % name):
                    # create a default view for the embedded document
                    field.field_type.add_view(name)
                todo.append((field_name, methodcaller))
            elif isinstance(field, ListField) and \
                    isinstance(field.subfield, EmbeddedDocumentField):

                if not hasattr(field.subfield.field_type, "%s_view_fields"
                        % name):
                    # create a default view for the embedded document
                    field.subfield.field_type.add_view(name)

                def loopcaller(value):
                    new_value = []
                    for elem in value:
                        new_value.append(methodcaller(elem))
                    return new_value

                todo.append((field_name, loopcaller))
            elif isinstance(field, MappingField) and \
                    isinstance(field.valuesubfield, EmbeddedDocumentField):

                if not hasattr(field.valuesubfield.field_type, "%s_view_fields"
                        % name):
                    # create a default view for the embedded document
                    field.valuesubfield.field_type.add_view(name)

                def mappingcaller(values):
                    new_values = {}
                    for key, value in values.items():
                        new_values[key] = methodcaller(value)
                    return new_values

                todo.append((field_name, mappingcaller))
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
