from enum import Enum
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionType(str, Enum):
    poi = "poi"
    attribute = "attribute"


# Create collection
class CreateCollectionRequest(BaseModel):
    collection_name: str = Field(..., description="Name of the Qdrant collection to create")
    collection_type: CollectionType = Field(..., description="Type of collection: 'poi' or 'attribute'")


# Upsert documents
class UpsertDocumentsBase(BaseModel):
    collection_name: str = Field(..., description="Target collection name")
    texts: list[str] = Field(..., description="List of text documents to index")
    ids: list[UUID] = Field(..., description="List of Qdrant point ids (UUID)")
    batch_size: int = Field(10, gt=0, description="Number of documents per upsert batch")


class UpsertPoiDocumentsRequest(UpsertDocumentsBase):
    collection_type: Literal[CollectionType.poi] = Field(
        ..., description="Type of collection: 'poi'"
    )
    poi_ids: list[str] = Field(..., description="List of poi ids for the documents")


class UpsertAttributeDocumentsRequest(UpsertDocumentsBase):
    collection_type: Literal[CollectionType.attribute] = Field(
        ..., description="Type of collection: 'attribute'"
    )
    attribute_ids: list[str] = Field(..., description="List of attribute ids for the documents")


UpsertDocumentsRequest = Annotated[
    Union[UpsertPoiDocumentsRequest, UpsertAttributeDocumentsRequest],
    Field(discriminator="collection_type"),
]
