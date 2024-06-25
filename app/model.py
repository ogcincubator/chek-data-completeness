# generated by datamodel-codegen:
#   filename:  schemas.yaml
#   timestamp: 2024-06-25T11:36:23+00:00

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Set

from pydantic import AnyUrl, BaseModel, Extra, Field, PositiveFloat, conint, RootModel, BaseConfig


class Model(BaseModel):
    class Config(BaseConfig):
        json_encoders = {
            BaseModel: lambda v: v.dict(exclude_unset=True)
        }


class Exception(Model):
    class Config:
        extra = Extra.allow

    type: str
    title: Optional[str] = None
    status: Optional[int] = None
    detail: Optional[str] = None
    instance: Optional[str] = None


class ConfClasses(Model):
    conformsTo: List[str]


class Response(Enum):
    raw = 'raw'
    document = 'document'


class Type(Enum):
    process = 'process'


class Link(Model):
    href: str
    rel: Optional[str] = Field(None, example='service')
    type: Optional[str] = Field(None, example='application/json')
    hreflang: Optional[str] = Field(None, example='en')
    title: Optional[str] = None


class MaxOccurs(Enum):
    unbounded = 'unbounded'


class Subscriber(Model):
    successUri: Optional[AnyUrl] = None
    inProgressUri: Optional[AnyUrl] = None
    failedUri: Optional[AnyUrl] = None


class StatusCode(Enum):
    accepted = 'accepted'
    running = 'running'
    successful = 'successful'
    failed = 'failed'
    dismissed = 'dismissed'


class JobControlOptions(Enum):
    sync_execute = 'sync-execute'
    async_execute = 'async-execute'
    dismiss = 'dismiss'


class TransmissionMode(Enum):
    value = 'value'
    reference = 'reference'


class Type1(Enum):
    array = 'array'
    boolean = 'boolean'
    integer = 'integer'
    number = 'number'
    object = 'object'
    string = 'string'


class Format(Model):
    mediaType: Optional[str] = None
    encoding: Optional[str] = None
    schema_: Optional[Union[str, Dict[str, Any]]] = Field(None, alias='schema')


class Metadata(Model):
    title: Optional[str] = None
    role: Optional[str] = None
    href: Optional[str] = None


class AdditionalParameter(Model):
    name: str
    value: List[Union[str, float, int, List[Dict[str, Any]], Dict[str, Any]]]


class Reference(Model):
    field_ref: str = Field(..., alias='$ref')


BinaryInputValue = RootModel[str]


class Crs(Enum):
    http___www_opengis_net_def_crs_OGC_1_3_CRS84 = (
        'http://www.opengis.net/def/crs/OGC/1.3/CRS84'
    )
    http___www_opengis_net_def_crs_OGC_0_CRS84h = (
        'http://www.opengis.net/def/crs/OGC/0/CRS84h'
    )


class Bbox(Model):
    bbox: List[float]
    crs: Optional[Crs] = 'http://www.opengis.net/def/crs/OGC/1.3/CRS84'


class LandingPage(Model):
    title: Optional[str] = Field(None, example='Example processing server')
    description: Optional[str] = Field(
        None, example='Example server implementing the OGC API - Processes 1.0 Standard'
    )
    links: List[Link]


class StatusInfo(Model):
    processID: Optional[str] = None
    type: Type
    jobID: str
    status: StatusCode
    message: Optional[str] = None
    created: Optional[datetime] = None
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    updated: Optional[datetime] = None
    progress: Optional[conint(ge=0, le=100)] = None
    links: Optional[List[Link]] = None


class Output(Model):
    format: Optional[Format] = None
    transmissionMode: Optional[TransmissionMode] = 'value'


class AdditionalParameters(Metadata):
    parameters: Optional[List[AdditionalParameter]] = None


class DescriptionType(Model):
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    metadata: Optional[List[Metadata]] = None
    additionalParameters: Optional[AdditionalParameters] = None


InputValueNoObject = RootModel[Union[str, float, int, bool, List[str], BinaryInputValue, Bbox]]

InputValue = RootModel[Union[InputValueNoObject, Dict[str, Any]]]


class JobList(Model):
    jobs: List[StatusInfo]
    links: List[Link]


class ProcessSummary(DescriptionType):
    id: str
    version: str
    jobControlOptions: Optional[List[JobControlOptions]] = None
    outputTransmission: Optional[List[TransmissionMode]] = None
    links: Optional[List[Link]] = None


class QualifiedInputValue(Format):
    value: InputValue


class ProcessList(Model):
    processes: List[ProcessSummary]
    links: List[Link]


InlineOrRefData = RootModel[Union[InputValueNoObject, QualifiedInputValue, Link]]


class Execute(Model):
    inputs: Optional[Dict[str, Union[InlineOrRefData, List[InlineOrRefData]]]] = None
    outputs: Optional[Dict[str, Output]] = None
    response: Optional[Response] = 'raw'
    subscriber: Optional[Subscriber] = None


Results = RootModel[Optional[Dict[str, InlineOrRefData]]]


InlineResponse200 = RootModel[Union[
    str, float, int, Dict[str, Any], List[Dict[str, Any]], bool, bytes, Results
]]


class Process(ProcessSummary):
    inputs: Optional[Dict[str, InputDescription]] = None
    outputs: Optional[Dict[str, OutputDescription]] = None


class InputDescription(DescriptionType):
    minOccurs: Optional[int] = 1
    maxOccurs: Optional[Union[int, MaxOccurs]] = None
    schema_: Schema = Field(..., alias='schema')


class OutputDescription(DescriptionType):
    schema_: Schema = Field(..., alias='schema')


class Schema1(Model):
    class Config:
        extra = Extra.forbid

    title: Optional[str] = None
    multipleOf: Optional[PositiveFloat] = None
    maximum: Optional[float] = None
    exclusiveMaximum: Optional[bool] = False
    minimum: Optional[float] = None
    exclusiveMinimum: Optional[bool] = False
    maxLength: Optional[conint(ge=0)] = None
    minLength: Optional[conint(ge=0)] = 0
    pattern: Optional[str] = None
    maxItems: Optional[conint(ge=0)] = None
    minItems: Optional[conint(ge=0)] = 0
    uniqueItems: Optional[bool] = False
    maxProperties: Optional[conint(ge=0)] = None
    minProperties: Optional[conint(ge=0)] = 0
    required: Optional[Set[str]] = Field(None, min_length=1)
    enum: Optional[Set[Dict[str, Any]]] = Field(None, min_length=1)
    type: Optional[Type1] = None
    not_: Optional[Union[Schema, Reference]] = Field(None, alias='not')
    allOf: Optional[List[Union[Schema, Reference]]] = None
    oneOf: Optional[List[Union[Schema, Reference]]] = None
    anyOf: Optional[List[Union[Schema, Reference]]] = None
    items: Optional[Union[Schema, Reference]] = None
    properties: Optional[Dict[str, Union[Schema, Reference]]] = None
    additionalProperties: Optional[Union[Schema, Reference, bool]] = True
    description: Optional[str] = None
    format: Optional[str] = None
    default: Optional[Dict[str, Any]] = None
    nullable: Optional[bool] = False
    readOnly: Optional[bool] = False
    writeOnly: Optional[bool] = False
    example: Optional[Dict[str, Any]] = None
    deprecated: Optional[bool] = False
    contentMediaType: Optional[str] = None
    contentEncoding: Optional[str] = None
    contentSchema: Optional[str] = None


Schema = RootModel[Union[Reference, Schema1]]


Process.update_forward_refs()
InputDescription.update_forward_refs()
OutputDescription.update_forward_refs()
Schema1.update_forward_refs()
