# Dico

After using [DictShield](https://github.com/j2labs/dictshield), a "database-agnostic modeling system", I've found the idea very usefull when dealing with NoSQL database, but want to choose another direction.
Dico is an attempt to solve my needs, heavily inspired by DictShield.

Most of the time you're manipulating data from a database server, modify it and save, especially in web development.

Here are the usual patterns with Dico:

### Create an object from scratch and validate fields

    from dico import *

    class BlogPost(Document):
       id = IntegerField()
       title = StringField(required=True, max_length=40)
       body = StringField(max_length=4096)
       creation_date = DateField(required=True, default=datetime.datetime.utcnow)

    >>> post = BlogPost()
    >>> post.body = 'I'm a new post'
    >>> post.validate()
    False

    >>> post.title = 'New post'
    >>> post.validate()
    True

    >>> post2 = BlogPost(title='Hop hop', body='thebody')

### Store it/Serialize it

    >>> post.to_dict()
    {'id': 45, 'title': 'New post', 'body': "I'm a new post"}

If ``to_dict`` is called with **invalid data** it will raise a
**ValidationException**.

### Validate an object populated from existing data and modify it

    >>> dict_from_db = {'id': '50000685467ffd11d1000001', 'title': 'A post', 'body': "I'm a post"}
    >>> post = BlogPost(**dict_from_db)
    >>> post.title
    "I'm a title from the DB"

    >>> post.title = 'New title from cli'
    >>> post.validate()
    True

### See modified fields since creation

    >>> post.modified_fields()
    ['title']

    # Usefull for Mongo update
    >>> post.to_dict(only_modified=True)
    {'title': 'New title from cli'}

Note that the result does not contain initially imported fields.

### Create an object with partial data
When working with real data, you will not fetch **every** fields from your DB, but still wants validation.

    >>> dict_from_db = {'body': "I'm a post"}
    >>> post = BlogPost(**dict_from_db)
    >>> post.validate()
    False

    >>> post.validate_partial()
    True

    >>> post2.BlogPost()
    >>> post2.title = 3
    >>> post2.validate_partial()
    False
    >>> post2.title = 'New title'
    >>> post2.validate_partial()
    True

### ListField
A list can contains n elements of a field's type.

    class User(Document):
        friends = ListField(IntegerField(), min_length=2, max_length=4)

### Field types

* BooleanField
* StringField
* IPAddressField
* URLField
* EmailField
* IntegerField
* FloatField
* DateTimeField
* ListField
* EmbeddedDocumentField

### Prepare object for export and adjust visibility of fields with views
Views are representation of the document.

    class User(Document):
        id = IntegerField(required=True)
        firstname = StringField(required=True, max_length=40)
        email = EmailField()

    User.add_view("public", ['firstname'])
    User.add_view("owner", remove_fields=['id'])

    >>> user = User(**dict_from_db)
    >>> user.to_owner()
    {'firstname': 'Paul', 'email':'paul_sponge@yahoo.com'}
    >>> user.to_public()
    {'firstname': 'Paul'}
    >> user.to_dict()
    {'firstname': 'Paul', 'email':'paul_sponge@yahoo.com', 'id': 56}

Note that ``to_dict`` is the default view method and returns the full
representation of the document.

### Import data from different sources

    class User(Document):
        id = IntegerField(required=True)
        firstname = StringField(required=True, max_length=40)
        position = StringField()

    User.add_source("owner", ["firstname"])

    >>> dict_from_post = {'firstname': 'Paul', 'position': 'team leader'}
    >>> user = User.from_owner(**dict_from_post)
    >>> user.to_dict()
    {'firstname': 'Paul'}
    >>> dict_from_database = {'id': 12, 'firstname': 'Jean'}
    >>> user = User.from_dict(**dict_from_database)
    >>> user.to_dict()
    {'id': 12, 'firstname': 'Jean'}

Note that ``from_dict`` is the default source method and imports every document
fields.

### Update a document for a source

    User.add_source("admin", ["firstname", "position"])

    >>> dict_from_admin = {'position': 'dev'}
    >>> user.update_from_admin(dict_from_api)
    >>> user.to_dict()
    {'id': 12, 'firstname': 'Jean', 'position': 'dev'}

### Filter
A Filter manipulates data before the import and after the export.

Here we are renaming *firstname* field to *first_name*::

    class User(Document):
        id = IntegerField()
        firstname = StringField(required=True, max_length=40)

        @staticmethod
        def save_filter(data):
            data['first_name] = data['firstname']
            del data['id']
            return data

    User.add_view("save", filter="save_filter")

    >>> user = User(firstname='Bob')
    >>> user.to_save()
    {'first_name':'Bob'}
    >>> user.to_dict()
    {'firstname':'Bob'}

There is a shortchut funcion for creating renaming filter called
``rename_field``.

    class User(Document):
        id = IntegerField()
        firstname = StringField(required=True, max_length=40)

    User.add_view("save", filter=rename_field('id', '_id'))

### @properties visibility
Properties are suitable for serialization

    class User(Document):
        firstname = StringField(required=True, max_length=40)
        lastname = StringField(required=True, max_length=40)

        @properties
        def full_name(self):
            return "%s %s" % (self.firstname, self.lastname)

    User.add_view("public", ["full_name"])

    >>> user.to_public()
    {'full_name': 'Sponge Bob'}

### Embedded fields
You may embed document in document, directly or within a list

    class OAuthToken(Document):
        consumer_secret = StringField(required=True, max_length=32)
        active = BooleanField(default=True)
        token_id = mongo.ObjectIdField(required=True, default=ObjectId)

    class User(Document):
        id = IntegerField()
        token = EmbeddedDocumentField(OAuthToken)

    >>> user = User()
    >>> user.token = 3
    >>> user.validate()
    False

    >>> user.token = OAuthToken()
    >>> user.validate()
    False
    >>> user.token = OAuthToken(consumer_secret='fac470fcd')
    >>> user.validate()
    False

    import dico.mongo

    class OAuthToken(Document):
        consumer_secret = StringField(required=True, max_length=32)
        active = BooleanField(default=True)
        token_id = dico.mongo.ObjectIdField(required=True, default=ObjectId)

    class User(Document):
        id = IntegerField()
        tokens = ListField(EmbeddedDocumentField(OAuthToken))

    >>> user = User()
    >>> user.id = 2

    >>> token = OAuthToken()
    >>> token.consumer_secret = 'fac470fcd'
    >>> token2 = OAuthToken()
    >>> token2.consumer_secret = 'fac470fcd'
    >>> user.tokens = [token, token2]

    # cascade recreate obj

    class OAuthToken(Document):
        consumer_secret = StringField()
        id = IntegerField()

    class User(Document):
        id = IntegerField()
        tokens = ListField(EmbeddedDocumentField(OAuthToken))

    >>> user_dict = {'id':1, 'tokens':[
            {'consumer_secret':'3fbc81fa', 'id':453245},
            {'consumer_secret':'bcd821s', 'id':98837}
        ] }

    >>> user = User(**user_dict)

    >>> user.tokens
    [<__main__.OAuthToken object at 0x109b3b390>, <__main__.OAuthToken object at 0x109b3b2c0>]

### Example usage with mongo
We know we want to update only some fields firstname and email, so we fetch the object with no field, update our fields then update, later we create a new user and save it.

    class User(Document):
        id = ObjectIdField(default=ObjectId(), required=True, aliases=['_id'])
        firstname = StringField(required=True, max_length=40)
        email = EmailField()

    User.add_source("db", filter=rename_field('_id', 'id'))

    User.add_view("db", filter=rename_field('id', '_id'))
    User.add_view("public", remove_fields=['email'])

    >>> user_dict = db.user.find_one({'email':'bob@sponge.com'})
    >>> user = User.from_db(**user_dict)
    >>> user.firstname = 'Bob'
    >>> user.email = 'bob@yahoo.com'
    >>> user.validate_partial()
    True
    >>> db.user.update({'_id': user.id}, user.to_db(only_modified=True))

    >>> user = User()
    >>> user.email = 'sponge@bob.com'
    >>> user.validate()
    True
    >>> db.user.save(user.to_db())

    # note this trick here we are reusing the public fields list from the user object to query only
    # this specific fields and make queries faster
    >>> user_dict = db.user.find_one({'email':'bob@yahoo.com'}, User.public_view_fields)
    >>> user = User(**user_dict)
    >>> user.to_public()
    {'id':'50000685467ffd11d1000001', 'firstname':'Bob'}

## Features

* required fields are checked for full object validation, but individual fields can be tested with `validate_partial`
* Document export using views (`to_dict` is the default view)
* Document import using sources (`from_dict` is the default source, also used by the constructor)
* Transform fields during import or export with the filter builder `format_field`
* Rename fields during import or export with the filter builder `rename_field`
* Track modified fields, for example to use update only changed fields with mongo
* Can serialize properties in views
* partial = not all fields, can create an object with only some fields you want to export (to avoid select * )
* Regexp compiled only one time
* use `__slots__` for memory optimization and to get on AttributeError on typo
* cascade creation of embedded oject

## Ideas
* Returns a representation of this Dico class as a JSON schema. (nizox)

## TODO
* Implements json compliant filters
* errors details
* the continue in `_validate_fields` does not show up in coverage
* update management for mongo ? (it will become a real ORM)
* how to deal with filters while subclassing ?

## Differences with dictshield
* dictshield raise ValueError while setting a property on a document if the data does not match the field, makes validate() useless
* dictshield allows unknown properties to be set
* dictshield does not use `__slots__`
* dictshield is more complete but complex
* dictshield has separates files in packages, makes import boring


## Installing

Dico is available via [pypi](http://pypi.python.org).

    pip install dico


## Change log
* 0.3 bugfix for mutable types
* 0.2 cascade creation, notify parent's document for modified fields, regexp stringfield now validate with '' (empty string)
* 0.1.1 fix important bugs, usable in production
* 0.1 initial release does not use in production

## Known bugs

## Contributors

* [Fabrice aneche](https://github.com/akhenakh)
* [Nicolas Vivet](https://github.com/nizox)
* [James Dennis](https://github.com/j2labs) for inspiration

## License

    * Copyright (c) 1998, Regents of the University of California
    * All rights reserved.
    * Redistribution and use in source and binary forms, with or without
    * modification, are permitted provided that the following conditions are met:
    *
    *     * Redistributions of source code must retain the above copyright
    *       notice, this list of conditions and the following disclaimer.
    *     * Redistributions in binary form must reproduce the above copyright
    *       notice, this list of conditions and the following disclaimer in the
    *       documentation and/or other materials provided with the distribution.
    *     * Neither the name of the University of California, Berkeley nor the
    *       names of its contributors may be used to endorse or promote products
    *       derived from this software without specific prior written permission.
    *
    * THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND ANY
    * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
    * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
    * DISCLAIMED. IN NO EVENT SHALL THE REGENTS AND CONTRIBUTORS BE LIABLE FOR ANY
    * DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
    * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
    * LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
    * ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
    * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
    * SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
