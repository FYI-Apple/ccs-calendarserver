##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from __future__ import absolute_import

"""
XML directory service implementation.
"""

__all__ = [
    "DirectoryService",
    "DirectoryRecord",
]

from xml.etree.ElementTree import parse as parseXML
from xml.etree.ElementTree import ParseError as XMLParseError

from twisted.python.constants import Values, ValueConstant

from twext.who.idirectory import RecordType, FieldName
from twext.who.idirectory import DirectoryServiceError
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.directory import DirectoryRecord



##
# XML Constants
##

class Element(Values):
    directory    = ValueConstant("directory")
    record       = ValueConstant("record")
    uid          = ValueConstant("uid")
    guid         = ValueConstant("guid")
    shortName    = ValueConstant("short-name")
    fullName     = ValueConstant("full-name")
    emailAddress = ValueConstant("email")
    password     = ValueConstant("password")
    member       = ValueConstant("member-uid")

    uid.fieldName          = FieldName.uid
    guid.fieldName         = FieldName.guid
    shortName.fieldName    = FieldName.shortNames
    fullName.fieldName     = FieldName.fullNames
    emailAddress.fieldName = FieldName.emailAddresses
    password.fieldName     = FieldName.password



class Attribute(Values):
    realm      = ValueConstant("realm")
    recordType = ValueConstant("type")



class Value(Values):
    # Booleans
    true  = ValueConstant("true")
    false = ValueConstant("false")

    # Record types
    user  = ValueConstant("user")
    group = ValueConstant("group")

    user.recordType  = RecordType.user
    group.recordType = RecordType.group



##
# Directory Service
##

class DirectoryService(BaseDirectoryService):
    """
    XML directory service.
    """

    ElementClass   = Element
    AttributeClass = Attribute
    ValueClass     = Value

    indexedFields = (
        FieldName.recordType,
        FieldName.uid,
        FieldName.guid,
        FieldName.shortNames,
        FieldName.emailAddresses,
    )


    def __init__(self, filePath, refreshInterval=4):
        BaseDirectoryService.__init__(self, realmName=None)

        self.filePath = filePath
        self.refreshInterval = refreshInterval


    def __repr__(self):
        return "<%s %s>" % (
            self.__class__.__name__,
            self._realmName,
        )


    @property
    def realmName(self):
        if not hasattr(self, "_realmName"):
            self.loadRecords()
        return self._realmName

    @realmName.setter
    def realmName(self, value):
        if value is not None:
            raise AssertionError("realmName may not be set directly")

    @property
    def unknownRecordTypes(self):
        if not hasattr(self, "_unknownRecordTypes"):
            self.loadRecords()
        return self._unknownRecordTypes

    @property
    def unknownFieldNames(self):
        if not hasattr(self, "_unknownFieldNames"):
            self.loadRecords()
        return self._unknownFieldNames

    @property
    def index(self):
        if not hasattr(self, "_index"):
            self.loadRecords()
        return self._index


    def loadRecords(self):
        #
        # Open and parse the file
        #
        try:
            fh = self.filePath.open()

            try:
                etree = parseXML(fh)
            except XMLParseError, e:
                raise DirectoryServiceError(e.getMessage())
        finally:
            fh.close()

        #
        # Pull data from DOM
        #
        directoryNode = etree.getroot()
        if directoryNode.tag != self.ElementClass.directory.value:
            raise DirectoryServiceError("Incorrect root element: %s" % (directoryNode.tag,))

        def getAttribute(node, name):
            return node.get(name, "").encode("utf-8")

        realmName = getAttribute(directoryNode, self.AttributeClass.realm.value)

        if not realmName:
            raise DirectoryServiceError("No realm name.")

        unknownRecordTypes = set()
        unknownFieldNames  = set()

        records = set()

        for recordNode in directoryNode.getchildren():
            recordTypeAttribute = getAttribute(recordNode, self.AttributeClass.recordType.value)
            if not recordTypeAttribute:
                recordTypeAttribute = "user"

            try:
                recordType = self.ValueClass.lookupByValue(recordTypeAttribute).recordType
            except (ValueError, AttributeError):
                unknownRecordTypes.add(recordTypeAttribute)
                break

            fields = {}
            fields[FieldName.recordType] = recordType

            for fieldNode in recordNode.getchildren():
                try:
                    fieldName = self.ElementClass.lookupByValue(fieldNode.tag).fieldName
                except (ValueError, AttributeError):
                    unknownFieldNames.add(fieldNode.tag)

                value = fieldNode.text.encode("utf-8")

                if self.FieldNameClass.isMultiValue(fieldName):
                    values = fields.setdefault(fieldName, [])
                    values.append(value)
                else:
                    fields[fieldName] = value

            records.add(DirectoryRecord(self, fields))

        #
        # Store results
        #

        index = {}

        for fieldName in self.indexedFields:
            index[fieldName] = {}

        for record in records:
            for fieldName in self.indexedFields:
                values = record.fields.get(fieldName, None)

                if values is not None:
                    if not self.FieldNameClass.isMultiValue(fieldName):
                        values = (values,)

                    for value in values:
                        index[fieldName].setdefault(value, set()).add(record)

        self._realmName = realmName

        self._unknownRecordTypes = unknownRecordTypes
        self._unknownFieldNames  = unknownFieldNames

        self._index = index
